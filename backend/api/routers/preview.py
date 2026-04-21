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
from api.services.ml_ranking import build_job_text_from_db
from api.services.ranking_adjust import adjusted_match_score
from api.services.ranking_explain import build_ranking_explanation
from src.inference.service import match_score
from src.matching.weak_score import (
    classify_job_skills,
    overlap_ratio,
    parse_skill_str,
)

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
    ranking_position: int           # estimated position if added
    total_ranked: int               # how many candidates already ranked for this job
    breakdown: MatchBreakdown
    matching_skills: List[str]
    missing_skills: List[str]
    missing_critical_skills: List[str]
    duplicate: Optional[DuplicateInfo] = None
    job_title: str = ""
    job_external_id: str = ""


# ── Endpoint ──────────────────────────────────────────────────

@router.post("/match/preview", response_model=MatchPreviewResponse, summary="Real-time match preview (no save)")
def match_preview(
    req: MatchPreviewRequest,
    db: Session = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
) -> MatchPreviewResponse:
    """
    Evaluate a candidate against a job in real-time without creating any database records.
    Returns match score, ranking breakdown, estimated ranking position, and duplicate detection.
    """
    # 1. Load job
    job = db.query(Job).filter(Job.external_id == req.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{req.job_id}' not found.")

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
        skills=req.candidate_skills or req.candidate_text[:500],
        raw_text=req.candidate_text,
        years_experience=req.years_experience,
        highest_degree=req.highest_degree or "",
        certifications=req.certifications or "",
    )

    # 4. Run cross-encoder match score
    job_text = build_job_text_from_db(job)
    try:
        raw_score: float = match_score(cand_text, job_text)
    except Exception as e:
        _log.warning("match_score failed in preview: %s — falling back to heuristic", e)
        raw_score = 0.5

    # 5. Compute adjusted final score
    adj = adjusted_match_score(
        job, cand_mock,
        raw_cross_encoder_score=raw_score,
        sbert_similarity=0.0,
    )
    final_score: float = adj["final_score"]

    # 6. Build explanation
    expl = build_ranking_explanation(
        job, cand_mock,
        cross_encoder_score=final_score,
        raw_cross_encoder_score=raw_score,
    )

    # 7. Compute skills overlap for the UI
    job_skills = parse_skill_str(job.skills or "")
    cand_skills = parse_skill_str(req.candidate_skills or "")
    _all_s, critical_s, _weights = classify_job_skills(job_skills)
    matching_skills: List[str] = sorted((job_skills & cand_skills))[:20]

    # 8. Estimate ranking position (how many existing ranked > this score)
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
