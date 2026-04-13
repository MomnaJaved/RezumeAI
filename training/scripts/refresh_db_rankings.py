#!/usr/bin/env python3
"""
1) create_all + ensure_extra_columns (same as API startup)
2) sync_enriched_to_postgres (jobs + candidates from CSV)
3) rank-and-save for every job in the DB (refreshes ranking snapshots)

Usage (repo root, venv active):
  python training/scripts/refresh_db_rankings.py
  TOP_K=30 python training/scripts/refresh_db_rankings.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT)

# noqa: E402 — path must be set first
from api.database import Base, SessionLocal, engine  # noqa: E402
from api.db_migrate import ensure_extra_columns  # noqa: E402
from api.models import Candidate, Job, JobCandidateRanking  # noqa: E402
from api.routers.rankings import _snapshot_role  # noqa: E402
from api.services.ranking_run import rank_for_external_job_id  # noqa: E402


def main() -> None:
    top_k = int(os.environ.get("TOP_K", "50"))

    print("Step 1: create_all + column migration...")
    Base.metadata.create_all(bind=engine)
    ensure_extra_columns(engine)
    print("  OK")

    print("Step 2: sync enriched CSVs → database...")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sync_mod", ROOT / "training" / "scripts" / "sync_enriched_to_postgres.py"
    )
    assert spec and spec.loader
    sync_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync_mod)
    sync_mod.main()
    print("  OK")

    print(f"Step 3: rank-and-save for each job (top_k={top_k})...")
    db = SessionLocal()
    try:
        jobs = db.query(Job).order_by(Job.external_id).all()
        if not jobs:
            print("  No jobs in DB; sync may have failed or CSV empty.")
            return
        for job in jobs:
            ext = job.external_id
            try:
                _, rows = rank_for_external_job_id(db, ext, top_k)
            except Exception as e:
                print(f"  SKIP {ext}: {e}")
                continue

            db.query(JobCandidateRanking).filter(JobCandidateRanking.job_id == job.id).delete()
            db.commit()

            run_at = datetime.utcnow()
            saved = 0
            for pos, r in enumerate(rows, start=1):
                cand = (
                    db.query(Candidate)
                    .filter(Candidate.external_id == r["candidate_id"])
                    .first()
                )
                if not cand:
                    continue
                snap_role = _snapshot_role(cand, r)
                db.add(
                    JobCandidateRanking(
                        job_id=job.id,
                        candidate_id=cand.id,
                        rank_position=pos,
                        cross_encoder_score=r["cross_encoder_score"],
                        sbert_similarity=r["sbert_similarity"],
                        candidate_name=r.get("candidate_name") or "",
                        candidate_title=r.get("candidate_title") or "",
                        candidate_role=snap_role,
                        years_experience=r.get("years_experience"),
                        highest_degree=r.get("highest_degree") or "",
                        skills_summary=r.get("skills_summary") or "",
                        run_at=run_at,
                    )
                )
                saved += 1
            db.commit()
            print(f"  {ext}: saved {saved} ranking rows")
    finally:
        db.close()

    print("Done.")


if __name__ == "__main__":
    main()
