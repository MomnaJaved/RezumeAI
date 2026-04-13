"""
Capture recruiter / reviewer actions on ranked lists (human-in-the-loop labels).

These rows are **not** applied online to model weights. They are stored for:
- FYP evaluation (compare model order vs human choice)
- Export → merge into training pairs with binary or graded relevance, then retrain.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Candidate, HumanRankingFeedback, Job
from api.schemas import HumanFeedbackCreate, HumanFeedbackRead
from api.services.feedback_actions import feedback_action_to_candidate_status

router = APIRouter(prefix="/feedback", tags=["feedback"])
_log = logging.getLogger("rezume.api")


@router.post("/ranking-selection", response_model=HumanFeedbackRead, status_code=201)
def record_ranking_selection(
    body: HumanFeedbackCreate,
    db: Session = Depends(get_db),
):
    """
    Call when a human **selects**, **shortlists**, or **rejects** a candidate
    for a job after seeing model rankings (UI button).

    Typical `action` values: `selected`, `shortlisted`, `rejected`, `not_a_fit`
    (free text allowed for experiments).
    """
    job = db.query(Job).filter(Job.external_id == body.job_external_id.strip()).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cand = (
        db.query(Candidate)
        .filter(Candidate.external_id == body.candidate_external_id.strip())
        .first()
    )
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    action_stored = body.action.strip()[:64]
    row = HumanRankingFeedback(
        job_id=job.id,
        candidate_id=cand.id,
        action=action_stored,
        rank_position_shown=body.rank_position_shown,
        model_score_at_feedback=body.model_score_at_feedback,
        notes=(body.notes or "")[:2000],
    )
    db.add(row)
    # Reflect latest hiring action on the candidate row (Candidates page status).
    cand.status = feedback_action_to_candidate_status(action_stored)[:64]
    db.commit()
    db.refresh(row)
    _log.info(
        "Human feedback job=%s cand=%s action=%s rank=%s",
        body.job_external_id,
        body.candidate_external_id,
        body.action,
        body.rank_position_shown,
    )
    return HumanFeedbackRead(
        id=row.id,
        job_external_id=job.external_id,
        candidate_external_id=cand.external_id,
        action=row.action,
        rank_position_shown=row.rank_position_shown,
        model_score_at_feedback=row.model_score_at_feedback,
        created_at=row.created_at,
    )


@router.get("/ranking-selection/summary")
def feedback_summary(db: Session = Depends(get_db)):
    """Light stats for demos / admin."""
    n = db.query(HumanRankingFeedback).count()
    return {"human_feedback_events_total": n}
