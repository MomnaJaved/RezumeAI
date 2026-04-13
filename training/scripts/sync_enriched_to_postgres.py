#!/usr/bin/env python3
"""
Upsert jobs and candidates from enriched CSVs into PostgreSQL.
Run after Postgres is up and DATABASE_URL is set in .env.

  python training/scripts/sync_enriched_to_postgres.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import pandas as pd  # noqa: E402

from api.database import SessionLocal  # noqa: E402
from api.models import Candidate, Job  # noqa: E402
from api.services.candidate_display import name_from_filename  # noqa: E402


def _years_from_row(row) -> Optional[float]:
    raw = row.get("years_experience_est", "")
    if raw == "" or raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def main() -> None:
    jobs_path = ROOT / "data" / "processed" / "jobs_enriched.csv"
    cands_path = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"
    if not jobs_path.exists():
        raise SystemExit(f"Missing {jobs_path}")
    if not cands_path.exists():
        raise SystemExit(f"Missing {cands_path}")

    jobs_df = pd.read_csv(jobs_path).fillna("")
    cands_df = pd.read_csv(cands_path).fillna("")

    db = SessionLocal()
    try:
        for _, row in jobs_df.iterrows():
            ext = str(row["job_id"])
            existing = db.query(Job).filter(Job.external_id == ext).first()
            min_exp = row.get("min_experience")
            try:
                min_exp_f = float(min_exp) if min_exp != "" else None
            except (TypeError, ValueError):
                min_exp_f = None
            if existing:
                existing.title = str(row.get("job_title", ""))
                existing.department = str(row.get("department", ""))
                existing.description = str(row.get("job_description_raw", ""))
                existing.skills = str(row.get("job_skills", ""))
                existing.min_experience = min_exp_f
                existing.education_required = str(row.get("education_required", "any") or "any")
            else:
                db.add(
                    Job(
                        external_id=ext,
                        title=str(row.get("job_title", "")),
                        department=str(row.get("department", "")),
                        description=str(row.get("job_description_raw", "")),
                        skills=str(row.get("job_skills", "")),
                        min_experience=min_exp_f,
                        education_required=str(row.get("education_required", "any") or "any"),
                    )
                )

        for _, row in cands_df.iterrows():
            ext = str(row["candidate_id"])
            fname = str(row.get("filename", ""))
            full_name = name_from_filename(fname)
            yexp = _years_from_row(row)
            hdeg = str(row.get("highest_degree", "") or "")
            existing = db.query(Candidate).filter(Candidate.external_id == ext).first()
            if existing:
                existing.full_name = full_name
                existing.title = str(row.get("title", ""))
                existing.skills = str(row.get("skills", ""))
                existing.raw_text = str(row.get("raw_text", ""))
                existing.filename = fname
                existing.years_experience = yexp
                existing.highest_degree = hdeg
            else:
                db.add(
                    Candidate(
                        external_id=ext,
                        full_name=full_name,
                        title=str(row.get("title", "")),
                        skills=str(row.get("skills", "")),
                        raw_text=str(row.get("raw_text", "")),
                        filename=fname,
                        years_experience=yexp,
                        highest_degree=hdeg,
                    )
                )

        db.commit()
        print(f"Synced {len(jobs_df)} jobs and {len(cands_df)} candidates.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
