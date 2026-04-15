#!/usr/bin/env python3
"""
Backfill Candidate.role_label from Candidate.title using src.parsing.role_labels.title_to_role_label.

Why: older ingests used the 3-class ML role classifier (frontend/backend/fullstack) and stored mixed-case
labels like "Other". The Candidates page role filter expects consistent, multi-department labels.

Usage:
  PYTHONPATH=backend:. python training/scripts/backfill_candidate_role_labels.py
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
from src.parsing.role_labels import ROLE_LABELS_MULTI, title_to_role_label  # noqa: E402


def _normalize(v: str) -> str:
    return (v or "").strip().lower()


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    ensure_extra_columns(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db: Session = SessionLocal()
    try:
        rows = db.query(Candidate).all()
        updated = 0
        for c in rows:
            title = (c.title or "").strip()
            if not title:
                continue
            new = title_to_role_label(title, multi_department=True)
            new = _normalize(new)
            if not new or new not in ROLE_LABELS_MULTI:
                new = "other"
            cur = _normalize(c.role_label)
            if cur != new:
                c.role_label = new
                updated += 1
        db.commit()
        print("candidates:", len(rows), "role_label updated:", updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()

