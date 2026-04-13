#!/usr/bin/env python3
"""
Dangerous helper: wipe candidate-related tables while keeping jobs.

Deletes (in safe order):
- job_candidate_rankings
- human_ranking_feedback
- resume_ingestions
- candidates

Works for SQLite (default ./rezume_dev.db) and Postgres (DATABASE_URL).

Usage:
  # Uses DATABASE_URL from .env, or defaults to SQLite rezume_dev.db
  PYTHONPATH=backend:. python training/scripts/clear_candidates.py --yes-really

  # Explicit URL (example)
  PYTHONPATH=backend:. python training/scripts/clear_candidates.py --yes-really \
    --database-url sqlite+pysqlite:///./rezume_dev.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from api.config import get_settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Delete candidates + related rows (keeps jobs).")
    ap.add_argument("--database-url", default=None, help="Override DATABASE_URL (otherwise uses .env/settings).")
    ap.add_argument(
        "--yes-really",
        action="store_true",
        help="Required. Without this flag the script exits without doing anything.",
    )
    args = ap.parse_args()

    if not args.yes_really:
        print("Refusing to run without --yes-really (this script destroys data).")
        raise SystemExit(2)

    get_settings.cache_clear()
    settings = get_settings()
    db_url = args.database_url or settings.database_url

    engine = create_engine(db_url, future=True)
    print("CLEARING CANDIDATES IN:", db_url)

    # SQLite may not enforce ON DELETE CASCADE unless foreign_keys=ON, so delete explicitly.
    stmts = [
        "DELETE FROM job_candidate_rankings",
        "DELETE FROM human_ranking_feedback",
        "DELETE FROM resume_ingestions",
        "DELETE FROM candidates",
    ]

    with engine.begin() as conn:
        for s in stmts:
            try:
                conn.execute(text(s))
            except Exception as e:
                # Table might not exist in older DBs; keep going.
                print(f"Skipping ({s}): {e}")

    print("Done. Candidate-related tables cleared.")


if __name__ == "__main__":
    main()

