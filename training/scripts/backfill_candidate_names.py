#!/usr/bin/env python3
"""
Recompute Candidate.full_name for broken placeholders (empty / "Candidate" / "Unknown Candidate")
using the same resolver as ingest: resume text, then email local-part, else "Unknown Candidate".

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
from src.parsing.name_extractor import resolve_candidate_full_name  # noqa: E402


def _needs_name_repair(stored: str) -> bool:
    s = (stored or "").strip().lower()
    return (not s) or s == "candidate" or s == "unknown candidate"


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
            cur = (c.full_name or "").strip()
            if not _needs_name_repair(cur):
                continue
            raw = (c.raw_text or "").strip()
            email = (c.contact_email or "").strip() or None
            new_name, _src = resolve_candidate_full_name(raw, email)
            if new_name != cur:
                c.full_name = new_name
                updated += 1
        db.commit()
        print("candidates:", len(rows), "full_name updated:", updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()
