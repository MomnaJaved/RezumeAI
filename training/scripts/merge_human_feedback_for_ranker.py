#!/usr/bin/env python3
"""
Join human feedback export to job_text + cand_text in the shape expected by
`training/scripts/train_match_ranker.py` (columns: job_text, cand_text, weak_score).

`weak_score` is mapped from `action` so the existing regression trainer can consume
the file without code changes:

  selected, hired, hired_interest → 1.0
  shortlisted → 0.85
  rejected, not_a_fit → 0.0

Usage (repo root, same DATABASE_URL as the API):

  PYTHONPATH=backend:. python training/scripts/merge_human_feedback_for_ranker.py

CSV-only (no DB), using enriched exports:

  PYTHONPATH=backend:. python training/scripts/merge_human_feedback_for_ranker.py \\
    --source csv \\
    --jobs-csv data/processed/jobs_enriched.csv \\
    --candidates-csv outputs/parsing/candidates_enriched.csv

Then fine-tune (example — keep silver val for eval if you have little human data):

  PYTHONPATH=. python training/scripts/train_match_ranker.py \\
    --train outputs/evaluation/human_feedback_for_ranker.csv \\
    --val outputs/transformer_data/val.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from src.preprocessing.pii import strip_pii  # noqa: E402


def _job_text_from_db(job) -> str:
    return " ".join(
        [
            str(job.title or ""),
            str(job.description or ""),
            str(job.skills or ""),
        ]
    ).strip()


def _cand_text_from_db(cand, strip_pii_text: bool) -> str:
    raw = " ".join(
        [
            str(cand.title or ""),
            str(cand.skills or ""),
            str(cand.raw_text or ""),
        ]
    ).strip()
    return strip_pii(raw) if strip_pii_text else raw


def _job_text_from_enriched_row(row: pd.Series) -> str:
    return " ".join(
        [
            str(row.get("job_title", "")),
            str(row.get("job_description_raw", "")),
            str(row.get("job_skills", "")),
        ]
    ).strip()


def _cand_text_from_enriched_row(row: pd.Series, strip_pii_text: bool) -> str:
    raw = " ".join(
        [
            str(row.get("title", "")),
            str(row.get("skills", "")),
            str(row.get("raw_text", "")),
        ]
    ).strip()
    return strip_pii(raw) if strip_pii_text else raw


def action_to_weak_score(action: str) -> float | None:
    a = (action or "").strip().lower().replace(" ", "_")
    if a in ("selected", "hired", "hired_interest", "hire", "yes"):
        return 1.0
    if a in ("shortlisted", "shortlist"):
        return 0.85
    if a in ("rejected", "reject", "not_a_fit", "no", "dismissed"):
        return 0.0
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge human feedback export for train_match_ranker")
    ap.add_argument(
        "--export",
        type=Path,
        default=ROOT / "outputs" / "evaluation" / "human_feedback_export.csv",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs" / "evaluation" / "human_feedback_for_ranker.csv",
    )
    ap.add_argument("--source", choices=("db", "csv"), default="db")
    ap.add_argument("--jobs-csv", type=Path, default=ROOT / "data" / "processed" / "jobs_enriched.csv")
    ap.add_argument(
        "--candidates-csv",
        type=Path,
        default=ROOT / "outputs" / "parsing" / "candidates_enriched.csv",
    )
    ap.add_argument(
        "--no-strip-pii",
        action="store_true",
        help="Disable PII stripping on candidate text (not recommended for training)",
    )
    ap.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Keep every event row (default: latest event per job+candidate wins)",
    )
    args = ap.parse_args()

    if not args.export.exists():
        raise SystemExit(f"Missing export: {args.export} (run export_human_feedback.py first)")

    df = pd.read_csv(args.export).fillna("")
    if df.empty:
        raise SystemExit("Export CSV is empty")

    strip_pii_text = not args.no_strip_pii

    rows_out: list[dict] = []

    if args.source == "db":
        from sqlalchemy.orm import Session  # noqa: E402

        from api.database import SessionLocal  # noqa: E402
        from api.models import Candidate, Job  # noqa: E402

        db: Session = SessionLocal()
        try:
            for _, r in df.iterrows():
                jid = str(r.get("job_external_id", "")).strip()
                cid = str(r.get("candidate_external_id", "")).strip()
                action = str(r.get("action", ""))
                w = action_to_weak_score(action)
                if w is None:
                    print("Skip unknown action:", action, "job=", jid, "cand=", cid)
                    continue
                job = db.query(Job).filter(Job.external_id == jid).first()
                cand = db.query(Candidate).filter(Candidate.external_id == cid).first()
                if not job or not cand:
                    print("Skip missing job/candidate in DB:", jid, cid)
                    continue
                rows_out.append(
                    {
                        "created_at": str(r.get("created_at", "")),
                        "job_id": jid,
                        "candidate_id": cid,
                        "job_text": _job_text_from_db(job),
                        "cand_text": _cand_text_from_db(cand, strip_pii_text),
                        "weak_score": w,
                        "action": action,
                        "rank_position_shown": r.get("rank_position_shown", ""),
                        "model_score_at_feedback": r.get("model_score_at_feedback", ""),
                    }
                )
        finally:
            db.close()
    else:
        if not args.jobs_csv.exists():
            raise SystemExit(f"Missing jobs CSV: {args.jobs_csv}")
        if not args.candidates_csv.exists():
            raise SystemExit(f"Missing candidates CSV: {args.candidates_csv}")

        jobs = pd.read_csv(args.jobs_csv).fillna("")
        cands = pd.read_csv(args.candidates_csv).fillna("")
        if "job_id" not in jobs.columns:
            raise SystemExit(f"jobs CSV needs job_id column: {args.jobs_csv}")
        if "candidate_id" not in cands.columns:
            raise SystemExit(f"candidates CSV needs candidate_id column: {args.candidates_csv}")

        job_by_ext = {str(r["job_id"]).strip(): r for _, r in jobs.iterrows()}
        cand_by_ext = {str(r["candidate_id"]).strip(): r for _, r in cands.iterrows()}

        for _, r in df.iterrows():
            jid = str(r.get("job_external_id", "")).strip()
            cid = str(r.get("candidate_external_id", "")).strip()
            action = str(r.get("action", ""))
            w = action_to_weak_score(action)
            if w is None:
                print("Skip unknown action:", action, "job=", jid, "cand=", cid)
                continue
            if jid not in job_by_ext or cid not in cand_by_ext:
                print("Skip missing job/candidate in CSV:", jid, cid)
                continue
            jr = job_by_ext[jid]
            cr = cand_by_ext[cid]
            rows_out.append(
                {
                    "created_at": str(r.get("created_at", "")),
                    "job_id": jid,
                    "candidate_id": cid,
                    "job_text": _job_text_from_enriched_row(jr),
                    "cand_text": _cand_text_from_enriched_row(cr, strip_pii_text),
                    "weak_score": w,
                    "action": action,
                    "rank_position_shown": r.get("rank_position_shown", ""),
                    "model_score_at_feedback": r.get("model_score_at_feedback", ""),
                }
            )

    if not rows_out:
        raise SystemExit("No rows produced (check actions, DB, or CSV keys)")

    out_df = pd.DataFrame(rows_out)

    if not args.no_dedupe and "created_at" in out_df.columns:
        # Latest event per (job_id, candidate_id)
        def _parse_ts(s: str) -> datetime:
            s = str(s).strip()
            if not s:
                return datetime.min
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return datetime.min

        out_df["_ts"] = out_df["created_at"].map(_parse_ts)
        out_df = out_df.sort_values("_ts").drop_duplicates(subset=["job_id", "candidate_id"], keep="last")
        out_df = out_df.drop(columns=["_ts"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False, quoting=csv.QUOTE_MINIMAL)
    print("Wrote", args.out, "rows=", len(out_df))


if __name__ == "__main__":
    main()
