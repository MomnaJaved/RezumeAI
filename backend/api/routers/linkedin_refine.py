"""
POST /api/v1/linkedin/refine-scrape
Optional xAI Grok cleanup of LinkedIn extension scrape → structured fields + candidate_text for matching.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.config import Settings, get_settings
from api.dependencies import get_current_user_optional
from api.models import User
from api.services.grok_linkedin_refine import refine_linkedin_scrape

router = APIRouter(prefix="/linkedin", tags=["linkedin"])


class LinkedInRefineRequest(BaseModel):
    raw_full_text: str = Field("", max_length=30000)
    raw_canonical: Optional[str] = Field(None, max_length=30000)
    profile_json: Optional[dict[str, Any]] = None
    name: Optional[str] = Field(None, max_length=512)
    title: Optional[str] = Field(None, max_length=512)
    location: Optional[str] = Field(None, max_length=256)
    email: Optional[str] = Field(None, max_length=320)
    skills: Optional[str] = Field(None, max_length=8000)
    years_experience: Optional[float] = Field(None, ge=0, le=80)
    highest_degree: Optional[str] = Field(None, max_length=256)
    certifications: Optional[str] = None
    profile_url: Optional[str] = Field(None, max_length=1024)


class LinkedInRefineResponse(BaseModel):
    refined_ok: bool
    skipped_reason: Optional[str] = None
    candidate_text: str = ""
    candidate_name: Optional[str] = None
    candidate_title: Optional[str] = None
    candidate_location: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_skills: Optional[str] = None
    certifications: Optional[str] = None
    about_summary: Optional[str] = None
    experience_block: Optional[str] = None
    education_block: Optional[str] = None
    years_experience: Optional[float] = None
    highest_degree: Optional[str] = None


@router.post("/refine-scrape", response_model=LinkedInRefineResponse, summary="Grok: refine LinkedIn scrape for matching")
def linkedin_refine_scrape(
    req: LinkedInRefineRequest,
    settings: Settings = Depends(get_settings),
    _user: Optional[User] = Depends(get_current_user_optional),
) -> LinkedInRefineResponse:
    payload = req.model_dump(exclude_none=True)
    out = refine_linkedin_scrape(settings, payload=payload)
    if not out.get("refined_ok"):
        return LinkedInRefineResponse(
            refined_ok=False,
            skipped_reason=str(out.get("skipped_reason") or "refine unavailable"),
        )
    return LinkedInRefineResponse(
        refined_ok=True,
        candidate_text=out.get("candidate_text") or "",
        candidate_name=out.get("candidate_name"),
        candidate_title=out.get("candidate_title"),
        candidate_location=out.get("candidate_location"),
        candidate_email=out.get("candidate_email"),
        candidate_skills=out.get("candidate_skills"),
        certifications=out.get("certifications"),
        about_summary=out.get("about_summary"),
        experience_block=out.get("experience_block"),
        education_block=out.get("education_block"),
        years_experience=out.get("years_experience"),
        highest_degree=out.get("highest_degree"),
    )
