"""Build display fields for ranking responses from DB rows or CSV."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from api.models import Candidate


def _truncate(text: str, max_len: int = 400) -> str:
    s = (text or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def name_from_filename(filename: str) -> str:
    if not filename or not str(filename).strip():
        return ""
    return Path(str(filename)).stem.replace("_", " ").strip()


def meta_from_candidate(cand: Candidate, fallback_id: str) -> dict[str, Any]:
    name = (cand.full_name or "").strip() or name_from_filename(cand.filename) or (cand.title or "").strip()
    if not name:
        name = fallback_id
    return {
        "candidate_name": name,
        "candidate_title": (cand.title or "").strip(),
        "candidate_role": (cand.role_label or "").strip(),
        "years_experience": cand.years_experience,
        "highest_degree": (cand.highest_degree or "").strip(),
        "skills_summary": _truncate(cand.skills or ""),
    }


def meta_from_csv_row(row: pd.Series, cand_ext: str) -> dict[str, Any]:
    title = str(row.get("title", "") or "").strip()
    fname = str(row.get("filename", "") or "")
    name = name_from_filename(fname) or title or cand_ext
    yexp: Optional[float] = None
    raw_y = row.get("years_experience_est", "")
    if raw_y != "" and raw_y is not None:
        try:
            yexp = float(raw_y)
        except (TypeError, ValueError):
            yexp = None
    return {
        "candidate_name": name,
        "candidate_title": title,
        "candidate_role": "",
        "years_experience": yexp,
        "highest_degree": str(row.get("highest_degree", "") or "").strip(),
        "skills_summary": _truncate(str(row.get("skills", "") or "")),
    }
