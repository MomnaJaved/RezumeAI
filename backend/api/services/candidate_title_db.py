"""DB-backed candidate title resolution (shared by ranking, SBERT, API)."""
from __future__ import annotations

from api.models import Candidate
from src.parsing.candidate_title_resolve import display_title_for_candidate_row


def resolved_display_title(c: Candidate) -> str:
    return display_title_for_candidate_row(
        title=str(getattr(c, "title", "") or ""),
        skills=str(getattr(c, "skills", "") or ""),
        years_experience=getattr(c, "years_experience", None),
        role_label=str(getattr(c, "role_label", "") or ""),
        raw_text=str(getattr(c, "raw_text", "") or ""),
    )
