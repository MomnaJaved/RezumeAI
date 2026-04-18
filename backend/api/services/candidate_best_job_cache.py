from __future__ import annotations

from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from api.models import Candidate, Job, JobCandidateRanking


def refresh_candidate_best_job_cache(db: Session, candidate_ids: Iterable[UUID]) -> None:
    """
    Recompute Candidate.best_job_match_score / best_job_external_id from persisted JobCandidateRanking rows.

    cross_encoder_score is stored on a 0–1 scale; Candidate.best_job_match_score is stored on a 0–100 scale.
    """
    ids = [cid for cid in candidate_ids if cid]
    if not ids:
        return

    rows = (
        db.query(JobCandidateRanking.candidate_id, Job.external_id, JobCandidateRanking.cross_encoder_score)
        .join(Job, Job.id == JobCandidateRanking.job_id)
        .filter(JobCandidateRanking.candidate_id.in_(ids))
        .all()
    )
    best_score: dict[UUID, float] = {}
    best_job_ext: dict[UUID, str] = {}
    for cid, ext, raw in rows:
        try:
            s01 = float(raw or 0.0)
        except Exception:
            s01 = 0.0
        s100 = max(0.0, min(100.0, s01 * 100.0))
        cur = best_score.get(cid, -1.0)
        if s100 > cur:
            best_score[cid] = s100
            best_job_ext[cid] = (ext or "").strip()

    for cid in ids:
        if cid in best_score:
            db.query(Candidate).filter(Candidate.id == cid).update(
                {
                    Candidate.best_job_match_score: float(best_score[cid]),
                    Candidate.best_job_external_id: best_job_ext.get(cid, "") or "",
                },
                synchronize_session=False,
            )
        else:
            db.query(Candidate).filter(Candidate.id == cid).update(
                {Candidate.best_job_match_score: None, Candidate.best_job_external_id: ""},
                synchronize_session=False,
            )

    db.commit()
