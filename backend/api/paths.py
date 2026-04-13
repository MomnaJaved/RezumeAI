"""Repository root: backend/api → parents[2] == RezumeAI project root."""
from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
