#!/usr/bin/env python3
"""
Recompute Candidate.full_name from raw_text using name_extractor (fixes older parses).

Usage:
  PYTHONPATH=backend:. python training/scripts/backfill_candidate_names.py
  (Runs from any directory; loads RezumeAI/.env via api.config.)
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
from src.parsing.name_extractor import extract_name_from_raw  # noqa: E402


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
            raw = (c.raw_text or "").strip()
            if not raw:
                continue
            new = extract_name_from_raw(raw)
            if not new:
                continue
            if (c.full_name or "").strip() != new:
                c.full_name = new
                updated += 1
        db.commit()
        print("candidates:", len(rows), "full_name updated:", updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()
