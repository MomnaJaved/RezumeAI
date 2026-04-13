#!/usr/bin/env python3
"""
Best-effort: backfill Candidate.storage_path from ResumeIngestion.storage_path
for already-ingested rows.

Usage:
  PYTHONPATH=backend:. python training/scripts/backfill_candidate_storage_paths.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, text  # noqa: E402

from api.config import get_settings  # noqa: E402
from api.db_migrate import ensure_extra_columns  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    db_url = settings.database_url
    engine = create_engine(db_url, future=True)
    ensure_extra_columns(engine)
    print("DB:", db_url)
    stmt = text(
        """
        UPDATE candidates
        SET storage_path = ri.storage_path
        FROM resume_ingestions ri
        WHERE candidates.external_id = ri.candidate_external_id
          AND COALESCE(candidates.storage_path, '') = ''
          AND COALESCE(ri.storage_path, '') <> ''
        """
    )
    with engine.begin() as conn:
        res = conn.execute(stmt)
        try:
            n = res.rowcount
        except Exception:
            n = None
    print("Backfilled rows:", n)


if __name__ == "__main__":
    main()

