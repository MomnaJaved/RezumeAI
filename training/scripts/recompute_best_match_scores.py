#!/usr/bin/env python3
"""
Compute and persist Candidate.best_job_match_score (0-100) against jobs in DB.

This makes list/dashboard endpoints fast while still using the real model scoring pipeline.

Usage:
  PYTHONPATH=backend:. python training/scripts/recompute_best_match_scores.py

Options:
  REZUME_BEST_MATCH_MAX_JOBS=25   # cap jobs considered (default 25)
  REZUME_BEST_MATCH_BATCH=48      # candidate batch size (default 48)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from api.config import get_settings  # noqa: E402
from api.db_migrate import ensure_extra_columns, ensure_indexes  # noqa: E402
from api.models import Candidate, Job  # noqa: E402
from api.services.model_match_score import best_job_match_scores_0_100  # noqa: E402


def _int_env(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)) or str(default))
        return v if v > 0 else default
    except ValueError:
        return default


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    ensure_extra_columns(engine)
    ensure_indexes(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db: Session = SessionLocal()
    try:
        max_jobs = _int_env("REZUME_BEST_MATCH_MAX_JOBS", 25)
        batch = _int_env("REZUME_BEST_MATCH_BATCH", 48)
        jobs = db.query(Job).filter(Job.status == "active").order_by(Job.created_at.desc()).limit(max_jobs).all()
        cands = db.query(Candidate).order_by(Candidate.created_at.desc()).all()
        updated = 0
        if not jobs or not cands:
            print("jobs:", len(jobs), "candidates:", len(cands), "updated:", 0)
            return

        # Score in batches (cross-encoder can be heavy).
        for start in range(0, len(cands), batch):
            chunk = cands[start : start + batch]
            scores, best_jobs, n_jobs = best_job_match_scores_0_100(db, chunk, jobs=jobs, max_jobs=max_jobs, batch_size=batch)
            if n_jobs <= 0:
                break
            for i, c in enumerate(chunk):
                sc = float(scores[i]) if i < len(scores) else 0.0
                bj = best_jobs[i] if i < len(best_jobs) else None
                prev = float(getattr(c, "best_job_match_score", 0.0) or 0.0)
                prev_j = (getattr(c, "best_job_external_id", "") or "").strip()
                if abs(prev - sc) > 0.01 or prev_j != (bj or ""):
                    c.best_job_match_score = sc
                    c.best_job_external_id = bj or ""
                    updated += 1
            db.commit()

        print("jobs:", len(jobs), "candidates:", len(cands), "updated:", updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()

