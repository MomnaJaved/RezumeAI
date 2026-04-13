#!/usr/bin/env python3
"""
Backfill Candidate.title using improved extractor, based on stored candidate.raw_text.

Usage:
  PYTHONPATH=backend:. python training/scripts/backfill_candidate_titles.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from api.config import get_settings  # noqa: E402
from api.db_migrate import ensure_extra_columns  # noqa: E402
from api.models import Candidate  # noqa: E402
from src.parsing.title_extractor import extract_title_from_raw  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    db_url = settings.database_url
    engine = create_engine(db_url, future=True)
    ensure_extra_columns(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db: Session = SessionLocal()
    try:
        rows = db.query(Candidate).all()
        updated = 0
        for c in rows:
            if (c.title or "").strip():
                continue
            t = extract_title_from_raw(c.raw_text or "")
            if t != "unknown" and t.strip():
                c.title = t
                updated += 1
        db.commit()
        print("candidates:", len(rows), "titles_backfilled:", updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()

