"""
Model-based matching utilities for Candidate ↔ Job scores.

We expose a lightweight "best match across jobs" score for list/dashboard views,
and a single-job match score is already available in ranking endpoints.
"""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from api.models import Candidate, Job
from api.services import ml_ranking


def _max_jobs_for_list() -> Optional[int]:
    raw = (os.environ.get("REZUME_BEST_MATCH_MAX_JOBS") or "").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def best_job_match_scores_0_100(
    db: Session,
    candidates: list[Candidate],
    *,
    jobs: Optional[list[Job]] = None,
    max_jobs: Optional[int] = None,
    batch_size: int = 48,
) -> tuple[list[float], list[Optional[str]], int]:
    """
    For each candidate, compute the best (max) cross-encoder match score vs jobs.
    Returns (scores_0_100, best_job_external_id_per_candidate, jobs_scored_count).

    Notes:
    - Uses cross-encoder via src.inference.service.match_scores_batch.
    - Scores are scaled to 0–100.
    - If there are no jobs with usable text, returns zeros and jobs_scored_count=0.
    """
    n = len(candidates)
    if n == 0:
        return [], None, 0

    # Collect jobs to score against.
    if jobs is None:
        q = db.query(Job).filter(Job.status == "active").order_by(Job.created_at.desc())
        cap = max_jobs if max_jobs is not None else _max_jobs_for_list()
        if cap is not None:
            q = q.limit(cap)
        jobs = list(q.all())
    jobs = [j for j in jobs if ml_ranking.build_job_text_from_db(j).strip()]
    if not jobs:
        return [0.0] * n, None, 0

    # Candidate texts once.
    cand_texts: list[str] = []
    for c in candidates:
        t = (ml_ranking.build_cand_text_from_db(c) or "").strip()
        cand_texts.append(t if t else " ")

    from src.inference.service import match_scores_batch

    best = [0.0] * n
    best_job_ext: list[Optional[str]] = [None] * n

    for job in jobs:
        jt = ml_ranking.build_job_text_from_db(job)
        # Score in batches to keep GPU/CPU memory bounded.
        for start in range(0, n, batch_size):
            chunk = cand_texts[start : start + batch_size]
            scores = match_scores_batch(jt, chunk, strip_pii_input=True, batch_size=min(batch_size, len(chunk)))
            for k, s in enumerate(scores):
                idx = start + k
                if idx >= n:
                    continue
                v = float(s) * 100.0
                if v > best[idx]:
                    best[idx] = v
                    best_job_ext[idx] = getattr(job, "external_id", None) or None

    return best, best_job_ext, len(jobs)

