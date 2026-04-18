"""DB-backed candidate title resolution (shared by ranking, SBERT, API)."""
from __future__ import annotations

from api.models import Candidate
from src.parsing.candidate_title_resolve import display_title_for_candidate_row


def resolved_display_title(c: Candidate) -> str:
    return display_title_for_candidate_row(
        title=getattr(c, "title", "") or "",
        skills=getattr(c, "skills", "") or "",
        years_experience=getattr(c, "years_experience", None),
        role_label=getattr(c, "role_label", "") or "",
        raw_text=getattr(c, "raw_text", "") or "",
    )
