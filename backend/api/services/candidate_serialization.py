"""Normalize Candidate ORM → CandidateRead payload (title fallback, TTL status, fresher hints)."""
from __future__ import annotations

from api.models import Candidate
from api.schemas import CandidateRead
from api.services.applicant_status_effective import effective_candidate_status
from api.services.candidate_title_display import polish_candidate_title
from api.services.candidate_title_db import resolved_display_title
from src.parsing.role_inference import infer_title_from_skills


def resolve_candidate_headline(c: Candidate) -> str:
    """
    Non-empty professional title for API + UI.
    Stored titles that polish to empty (noise/garbage) are replaced with the same inference
    pipeline used at ingest (skills, raw_text, role_label).
    """
    stored = (getattr(c, "title", None) or "").strip()
    polished_stored = polish_candidate_title(stored) if stored else ""
    if polished_stored:
        return polished_stored
    inferred = resolved_display_title(c)
    polished_inf = polish_candidate_title(inferred) if inferred else ""
    out = polished_inf or inferred or "Professional"
    return out if (out or "").strip() else "Professional"


def candidate_read_dict(c: Candidate) -> dict:
    d = CandidateRead.model_validate(c).model_dump()
    d["title"] = resolve_candidate_headline(c)
    d["status_effective"] = effective_candidate_status(getattr(c, "status", None), getattr(c, "created_at", None))
    d["skills_role_hint"] = None
    if (d.get("title") or "").strip().lower() == "fresher":
        hint = infer_title_from_skills(c.skills or "")
        if hint and hint.lower() != "unknown":
            d["skills_role_hint"] = hint.replace("_", " ").title()
    return d
