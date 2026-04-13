#!/usr/bin/env python3
"""Create PostgreSQL tables from SQLAlchemy models (idempotent)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from api.database import Base, engine  # noqa: E402


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Tables created (or already exist).")


if __name__ == "__main__":
    main()
