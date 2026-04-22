"""
POST /api/v1/match/preview
Real-time candidate ranking without database persistence.
Used by the Chrome extension to evaluate a candidate against a job
before deciding whether to save them.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import List, Optional

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

@router.post("/match/preview", response_model=MatchPreviewResponse, summary="Real-time match preview (no save)")
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
        raw_score: float = match_score(cand_text, job_text)
    except Exception as e:
        _log.warning("match_score failed in preview: %s — falling back to heuristic", e)
        raw_score = 0.5

    job_vec = job_text_embedding(job_text)
    sem_preview = semantic_similarity_for_text(job_vec, cand_text)
    adj = adjusted_match_score(
        job,
        cand_mock,
        raw_cross_encoder_score=raw_score,
        sbert_similarity=sem_preview,
    )
    final_score: float = float(adj["final_score"])

    # 6. Build explanation
    expl = build_ranking_explanation(
        job, cand_mock,
        cross_encoder_score=final_score,
        raw_cross_encoder_score=float(adj.get("raw_cross_encoder_score", raw_score)),
    )

    # 7. Compute skills overlap for the UI
    job_skills = parse_skill_str(job.skills or "")
    cand_skills = parse_skill_str(req.candidate_skills or "")
    _all_s, critical_s, _weights = classify_job_skills(job_skills)
    matching_skills: List[str] = sorted((job_skills & cand_skills))[:20]

    # 8. Rank vs full workspace candidate pool (recruiter), else saved rankings only
    pool_capped = False
    pool_scope = "saved_rankings_only"
    role = (getattr(user, "account_role", None) or "none").strip().lower() if user else "none"
    recruiter_ws = None
    if user is not None and role != "candidate":
        recruiter_ws = ensure_workspace_for_recruiter(db, user)

    if recruiter_ws is not None:
        pool_scope = "workspace_pool"
        ranking_position, total_ranked, pool_capped, _n = workspace_pool_rank(
            db,
            job,
            job_text,
            job_vec,
            final_score,
            workspace_id=recruiter_ws,
        )
    else:
        existing = (
            db.query(JobCandidateRanking.cross_encoder_score)
            .filter(JobCandidateRanking.job_id == job.id)
            .all()
        )
        existing_scores = [row[0] for row in existing]
        ranking_position = sum(1 for s in existing_scores if s > final_score) + 1
        total_ranked = len(existing_scores)

    # 9. Duplicate detection (by email then by profile URL)
    duplicate: Optional[DuplicateInfo] = None
    if req.candidate_email and req.candidate_email.strip():
        dup = (
            db.query(Candidate)
            .filter(Candidate.contact_email == req.candidate_email.strip().lower())
            .first()
        )
        if dup:
            duplicate = DuplicateInfo(
                external_id=dup.external_id,
                full_name=dup.full_name or "",
                existing_match_score=(
                    round(float(dup.best_job_match_score) * 100, 1)
                    if dup.best_job_match_score is not None
                    else None
                ),
            )

    # 10. Title relevance normalised to 0–1 for UI display
    title_rel_raw: float = float(adj.get("role_relevance_adjust", 0.0))
    title_rel_norm = round(min(1.0, max(0.0, (title_rel_raw + 0.30) / 0.45)), 4)

    score_pct = round(final_score * 100, 1)
    if score_pct >= 70:
        label = "Strong"
    elif score_pct >= 45:
        label = "Medium"
    else:
        label = "Weak"

    return MatchPreviewResponse(
        match_score=score_pct,
        match_label=label,
        ranking_position=ranking_position,
        total_ranked=total_ranked,
        pool_ranking_scope=pool_scope,
        pool_capped=pool_capped,
        breakdown=MatchBreakdown(
            skills_overlap=round(float(expl["skills_match_ratio"]), 4),
            critical_skill_coverage=round(float(expl["critical_skill_coverage"]), 4),
            experience_match=round(float(expl["experience_match"]), 4),
            education_match=round(float(expl["education_match"]), 4),
            title_relevance=title_rel_norm,
            heuristic_score=round(float(expl["heuristic_weak_score"]), 4),
        ),
        matching_skills=matching_skills,
        missing_skills=expl["missing_skills"][:15],
        missing_critical_skills=expl["missing_critical_skills"][:10],
        duplicate=duplicate,
        job_title=job.title or "",
        job_external_id=job.external_id or "",
    )
