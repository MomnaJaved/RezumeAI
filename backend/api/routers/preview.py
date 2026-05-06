"""
POST /api/v1/match/preview
Real-time candidate ranking without database persistence.
Used by the Chrome extension to evaluate a candidate against a job
before deciding whether to save them.
"""
from __future__ import annotations

import logging
import math
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_current_user_optional
from api.models import Candidate, Job, JobCandidateRanking, User
from api.services.match_preview_pool import job_text_embedding, semantic_similarity_for_text, workspace_pool_rank
from api.services.ml_ranking import build_job_text_from_db
from api.services.ranking_adjust import adjusted_match_score
from api.services.ranking_explain import build_ranking_explanation
from api.services.workspace_scope import ensure_workspace_for_recruiter
from src.inference.service import match_score
from src.matching.weak_score import classify_job_skills, parse_skill_str

_log = logging.getLogger("rezume.api")

router = APIRouter(tags=["match-preview"])


def _preview_position_vs_saved_rankings(db: Session, job: Job, final_score: float) -> tuple[int, int]:
    existing = (
        db.query(JobCandidateRanking.cross_encoder_score)
        .filter(JobCandidateRanking.job_id == job.id)
        .all()
    )
    existing_scores: List[float] = []
    for row in existing:
        s = row[0]
        if s is None:
            continue
        try:
            existing_scores.append(float(s))
        except (TypeError, ValueError):
            continue
    ranking_position = sum(1 for s in existing_scores if s > final_score) + 1
    total_ranked = len(existing_scores)
    return ranking_position, total_ranked


def _finite_float(x: object, default: float = 0.0) -> float:
    """JSON-serializable float (NaN/inf break FastAPI response encoding)."""
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return v


def _str_skill_list(xs: object, *, limit: int) -> List[str]:
    """Ensure OpenAPI `List[str]` even if upstream returns mixed types."""
    if not xs:
        return []
    seq = xs if isinstance(xs, (list, tuple)) else []
    out: List[str] = []
    for x in seq:
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


# ── Request / Response schemas ────────────────────────────────

class MatchPreviewRequest(BaseModel):
    """Candidate data extracted from a profile page — nothing is persisted."""
    job_id: str = Field(..., description="Job external_id to match against")
    candidate_text: str = Field(..., min_length=10, description="Full resume / profile text")
    candidate_name: Optional[str] = Field(None, max_length=512)
    candidate_title: Optional[str] = Field(None, max_length=512)
    candidate_skills: Optional[str] = Field(None, description="Comma-separated skills")
    candidate_email: Optional[str] = Field(None, max_length=320, description="Used for duplicate detection")
    candidate_location: Optional[str] = Field(None, max_length=256)
    years_experience: Optional[float] = Field(None, ge=0)
    highest_degree: Optional[str] = Field(None, max_length=256)
    certifications: Optional[str] = Field(None)
    profile_url: Optional[str] = Field(None, max_length=1024)


class MatchBreakdown(BaseModel):
    skills_overlap: float       # 0–1: job skill coverage
    critical_skill_coverage: float
    experience_match: float     # 0–1
    education_match: float      # 0–1
    title_relevance: float      # -0.3 – +0.15 normalised to 0–1
    heuristic_score: float      # 0–1 composite


class DuplicateInfo(BaseModel):
    external_id: str
    full_name: str
    existing_match_score: Optional[float] = None


class MatchPreviewResponse(BaseModel):
    match_score: float              # 0–100
    match_label: str                # Strong / Medium / Weak
    ranking_position: int           # 1-based rank vs pool (see pool_ranking_scope)
    total_ranked: int               # pool size: workspace candidates scored, or saved rankings only
    pool_ranking_scope: str = Field(
        "",
        description="workspace_pool = ranked vs all visible candidates; saved_rankings_only = JobCandidateRanking rows only",
    )
    pool_capped: bool = Field(False, description="True if workspace pool hit REZUME_MATCH_PREVIEW_POOL_CAP")
    breakdown: MatchBreakdown
    matching_skills: List[str]
    missing_skills: List[str]
    missing_critical_skills: List[str]
    duplicate: Optional[DuplicateInfo] = None
    job_title: str = ""
    job_external_id: str = ""


# ── Endpoint ──────────────────────────────────────────────────

def _preview_enforce_job_access(db: Session, job: Job, user: Optional[User]) -> None:
    if user is None:
        return
    if (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() == "candidate":
        return
    w = ensure_workspace_for_recruiter(db, user)
    if w is not None:
        jw = getattr(job, "workspace_id", None)
        if jw is not None and jw != w:
            raise HTTPException(status_code=404, detail=f"Job '{job.external_id}' not found.")


@router.post("/match/preview", response_model=MatchPreviewResponse, summary="Real-time match preview (no save)")
def match_preview(
    req: MatchPreviewRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> MatchPreviewResponse:
    """
    Evaluate a candidate against a job in real-time without creating any database records.
    Match % uses the same adjusted path as saved rankings (cross-encoder + semantic SBERT term
    + skill / experience rules). Rank is vs all workspace-visible candidates when authenticated
    as a recruiter; otherwise vs stored JobCandidateRanking rows only.
    """
    # 1. Load job
    job = db.query(Job).filter(Job.external_id == req.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{req.job_id}' not found.")
    _preview_enforce_job_access(db, job, user)

    # 2. Build candidate text (structured fields improve scoring)
    cand_text_parts = [
        req.candidate_title or "",
        req.candidate_skills or "",
        req.candidate_text or "",
    ]
    cand_text = " ".join(p for p in cand_text_parts if p).strip()
    if not cand_text:
        raise HTTPException(status_code=422, detail="candidate_text is required.")

    # 3. Build a lightweight mock candidate object (no DB write)
    cand_mock = SimpleNamespace(
        title=req.candidate_title or "",
        skills=req.candidate_skills or "",
        raw_text=req.candidate_text,
        years_experience=req.years_experience,
        highest_degree=req.highest_degree or "",
        certifications=req.certifications or "",
    )

    # 4. Run cross-encoder match score + adjusted final (incl. semantic, same family as rank-and-save)
    job_text = build_job_text_from_db(job)
    try:
        raw_score = _finite_float(match_score(cand_text, job_text), 0.5)
    except Exception as e:
        _log.warning("match_score failed in preview: %s — falling back to heuristic", e)
        raw_score = 0.5

    job_vec: np.ndarray
    sem_preview: float
    try:
        job_vec = job_text_embedding(job_text)
        sem_preview = _finite_float(semantic_similarity_for_text(job_vec, cand_text), 0.0)
    except Exception as e:
        _log.warning("preview: SBERT embedding/similarity skipped: %s", e)
        job_vec = np.zeros(384, dtype=np.float32)
        sem_preview = 0.0

    try:
        adj = adjusted_match_score(
            job,
            cand_mock,
            raw_cross_encoder_score=raw_score,
            sbert_similarity=sem_preview,
        )
        final_score = _finite_float(adj.get("final_score"), 0.5)
    except Exception as e:
        _log.warning("preview: adjusted_match_score failed: %s", e)
        adj = {"final_score": raw_score, "raw_cross_encoder_score": raw_score, "role_relevance_adjust": 0.0}
        final_score = _finite_float(raw_score, 0.5)

    # 6. Build explanation
    try:
        expl: Dict[str, Any] = build_ranking_explanation(
            job,
            cand_mock,
            _finite_float(final_score, 0.5),
            raw_cross_encoder_score=_finite_float(adj.get("raw_cross_encoder_score", raw_score), raw_score),
        )
    except Exception as e:
        _log.warning("preview: build_ranking_explanation failed: %s", e)
        expl = {
            "skills_match_ratio": 0.0,
            "critical_skill_coverage": 0.0,
            "experience_match": 0.0,
            "education_match": 0.0,
            "heuristic_weak_score": 0.0,
            "missing_skills": [],
            "missing_critical_skills": [],
        }

    # 7. Compute skills overlap for the UI
    try:
        job_skills = parse_skill_str(str(job.skills or ""))
        cand_skills = parse_skill_str(str(req.candidate_skills or ""))
        _all_s, critical_s, _weights = classify_job_skills(job_skills)
        matching_skills: List[str] = sorted((job_skills & cand_skills))[:20]
    except Exception as e:
        _log.warning("preview: skills overlap step failed: %s", e)
        matching_skills = []

    # 8. Rank vs full workspace candidate pool (recruiter), else saved rankings only
    pool_capped = False
    pool_scope = "saved_rankings_only"
    role = (getattr(user, "account_role", None) or "none").strip().lower() if user else "none"
    recruiter_ws = None
    if user is not None and role != "candidate":
        recruiter_ws = ensure_workspace_for_recruiter(db, user)

    if recruiter_ws is not None:
        pool_scope = "workspace_pool"
        try:
            ranking_position, total_ranked, pool_capped, _n = workspace_pool_rank(
                db,
                job,
                job_text,
                job_vec,
                final_score,
                workspace_id=recruiter_ws,
            )
        except Exception as e:
            _log.warning("preview: workspace_pool_rank failed; using saved rankings only: %s", e)
            pool_scope = "saved_rankings_only"
            pool_capped = False
            ranking_position, total_ranked = _preview_position_vs_saved_rankings(db, job, final_score)
    else:
        ranking_position, total_ranked = _preview_position_vs_saved_rankings(db, job, final_score)

    # 9. Duplicate detection (by email then by profile URL)
    duplicate: Optional[DuplicateInfo] = None
    if req.candidate_email and req.candidate_email.strip():
        dup = (
            db.query(Candidate)
            .filter(Candidate.contact_email == req.candidate_email.strip().lower())
            .first()
        )
        if dup:
            ext_dup = (getattr(dup, "external_id", None) or "").strip()
            if ext_dup:
                dup_pct: Optional[float] = None
                if dup.best_job_match_score is not None:
                    try:
                        raw_p = float(dup.best_job_match_score) * 100
                        if math.isfinite(raw_p):
                            dup_pct = round(raw_p, 1)
                    except (TypeError, ValueError):
                        dup_pct = None
                duplicate = DuplicateInfo(
                    external_id=ext_dup,
                    full_name=(dup.full_name or "") or "",
                    existing_match_score=dup_pct,
                )

    # 10. Title relevance normalised to 0–1 for UI display
    title_rel_raw = _finite_float(adj.get("role_relevance_adjust", 0.0), 0.0)
    title_rel_norm = round(min(1.0, max(0.0, (title_rel_raw + 0.30) / 0.45)), 4)

    score_pct = round(_finite_float(final_score, 0.0) * 100, 1)
    if score_pct >= 70:
        label = "Strong"
    elif score_pct >= 45:
        label = "Medium"
    else:
        label = "Weak"

    return MatchPreviewResponse(
        match_score=float(score_pct),
        match_label=label,
        ranking_position=int(ranking_position),
        total_ranked=int(total_ranked),
        pool_ranking_scope=str(pool_scope or ""),
        pool_capped=bool(pool_capped),
        breakdown=MatchBreakdown(
            skills_overlap=round(_finite_float(expl.get("skills_match_ratio"), 0.0), 4),
            critical_skill_coverage=round(_finite_float(expl.get("critical_skill_coverage"), 0.0), 4),
            experience_match=round(_finite_float(expl.get("experience_match"), 0.0), 4),
            education_match=round(_finite_float(expl.get("education_match"), 0.0), 4),
            title_relevance=title_rel_norm,
            heuristic_score=round(_finite_float(expl.get("heuristic_weak_score"), 0.0), 4),
        ),
        matching_skills=_str_skill_list(matching_skills, limit=20),
        missing_skills=_str_skill_list(expl.get("missing_skills"), limit=15),
        missing_critical_skills=_str_skill_list(expl.get("missing_critical_skills"), limit=10),
        duplicate=duplicate,
        job_title=str(job.title or ""),
        job_external_id=str(job.external_id or ""),
    )
