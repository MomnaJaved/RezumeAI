#!/usr/bin/env python3
"""
Export human_ranking_feedback rows to CSV for building labeled pair data.

Usage (repo root, DATABASE_URL in env matching the API DB):
  PYTHONPATH=backend:. python training/scripts/export_human_feedback.py

Output: outputs/evaluation/human_feedback_export.csv

Merge strategy (FYP):
  - Rows with action in (selected, shortlisted, hired_interest) → relevance label 1
  - rejected / not_a_fit → label 0
  - Join job_text + cand_text from DB or enriched CSVs for train_match_ranker fine-tune
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.orm import Session  # noqa: E402

from api.database import SessionLocal  # noqa: E402
from api.models import Candidate, HumanRankingFeedback, Job  # noqa: E402


def main() -> None:
    out_dir = ROOT / "outputs" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "human_feedback_export.csv"

    db: Session = SessionLocal()
    try:
        rows = db.query(HumanRankingFeedback).order_by(HumanRankingFeedback.created_at).all()
        if not rows:
            print("No human_ranking_feedback rows. Use POST /api/v1/feedback/ranking-selection first.")
            return

        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "created_at",
                    "job_external_id",
                    "candidate_external_id",
                    "action",
                    "rank_position_shown",
                    "model_score_at_feedback",
                    "notes",
                ]
            )
            for r in rows:
                job = db.query(Job).filter(Job.id == r.job_id).first()
                cand = db.query(Candidate).filter(Candidate.id == r.candidate_id).first()
                w.writerow(
                    [
                        r.created_at.isoformat() if r.created_at else "",
                        job.external_id if job else "",
                        cand.external_id if cand else "",
                        r.action,
                        r.rank_position_shown or "",
                        r.model_score_at_feedback if r.model_score_at_feedback is not None else "",
                        (r.notes or "").replace("\n", " ")[:500],
                    ]
                )
        print("Wrote", out_path, "rows=", len(rows))
    finally:
        db.close()


if __name__ == "__main__":
    main()
