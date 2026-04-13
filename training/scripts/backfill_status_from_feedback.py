#!/usr/bin/env python3
"""
Set Candidate.status from each candidate's most recent human_ranking_feedback row.

Run once after deploying feedback→status sync, or to repair rows.

Usage:
  PYTHONPATH=backend:. python training/scripts/backfill_status_from_feedback.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from api.config import get_settings  # noqa: E402
from api.db_migrate import ensure_extra_columns  # noqa: E402
from api.models import Candidate, HumanRankingFeedback  # noqa: E402
from api.services.feedback_actions import feedback_action_to_candidate_status  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    ensure_extra_columns(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db: Session = SessionLocal()
    try:
        cand_ids = {row[0] for row in db.query(HumanRankingFeedback.candidate_id).distinct().all()}
        updated = 0
        for cid in cand_ids:
            last = (
                db.query(HumanRankingFeedback)
                .filter(HumanRankingFeedback.candidate_id == cid)
                .order_by(HumanRankingFeedback.created_at.desc())
                .first()
            )
            if not last:
                continue
            cand = db.query(Candidate).filter(Candidate.id == cid).first()
            if not cand:
                continue
            new_status = feedback_action_to_candidate_status(last.action)[:64]
            if (cand.status or "") != new_status:
                cand.status = new_status
                updated += 1
        db.commit()
        print("candidates_with_feedback:", len(cand_ids), "status rows updated:", updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()
