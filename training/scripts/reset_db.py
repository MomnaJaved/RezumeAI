#!/usr/bin/env python3
"""
Dangerous helper: wipe the API database after training.

Use-case: you trained on a large synced corpus, but for demo/testing you want a clean DB.

This script DROPS ALL TABLES for the configured DATABASE_URL and recreates them.
It does not delete your CSV files or model artifacts.

Usage:
  # Postgres (DATABASE_URL from .env)
  PYTHONPATH=backend:. python training/scripts/reset_db.py --yes-really

  # Explicit URL (example)
  PYTHONPATH=backend:. python training/scripts/reset_db.py --yes-really \\
    --database-url postgresql+psycopg2://rezume:rezume@localhost:5432/rezumeai
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine  # noqa: E402

from api.config import get_settings  # noqa: E402
from api.database import Base  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Wipe all DB tables (DROP + CREATE).")
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
    print("WIPING DATABASE:", db_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Done. All tables dropped and recreated.")


if __name__ == "__main__":
    main()

