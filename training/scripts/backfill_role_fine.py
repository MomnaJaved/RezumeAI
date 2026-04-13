#!/usr/bin/env python3
"""
Backfill Candidate.role_fine for existing rows.

Usage:
  PYTHONPATH=backend:. python training/scripts/backfill_role_fine.py
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
from src.parsing.role_fine import infer_role_fine  # noqa: E402


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
            new = infer_role_fine(c.title or "", c.skills or "", raw_hint=(c.raw_text or "")[:5000])
            if (c.role_fine or "") != new:
                c.role_fine = new
                updated += 1
        db.commit()
        print("candidates:", len(rows), "updated:", updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()

