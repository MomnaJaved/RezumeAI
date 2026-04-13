"""Pydantic schemas for API requests and responses."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- ML ---
class ClassifyRoleRequest(BaseModel):
    resume_text: str


class ClassifyRoleResponse(BaseModel):
    label: str
    probs: Dict[str, float]


class MatchScoreRequest(BaseModel):
    resume_text: str
    jd_text: str


class MatchScoreResponse(BaseModel):
    score: float


class RankCandidatesRequest(BaseModel):
    job_id: str = Field(..., description="External job id e.g. J001")
    top_k: int = 50


class RankingExplanationOut(BaseModel):
    """Heuristic breakdown + model score (not a second neural model)."""

    skills_match_ratio: float
    experience_match: float
    education_match: float
    heuristic_weak_score: float
    missing_skills: List[str]
    cross_encoder_score: float


class RankedCandidateOut(BaseModel):
    candidate_id: str
    cross_encoder_score: float
    sbert_similarity: float
    candidate_name: str = ""
    candidate_title: str = ""
    candidate_role: str = ""
    years_experience: Optional[float] = None
    highest_degree: str = ""
    skills_summary: str = ""
    explanation: Optional[RankingExplanationOut] = None


class RankCandidatesResponse(BaseModel):
    job_id: str
    candidates: List[RankedCandidateOut]


# --- Jobs ---
class JobCreate(BaseModel):
    external_id: str
    title: str = ""
    department: str = ""
    description: str = ""
    skills: str = ""
    min_experience: Optional[float] = None
    education_required: str = "any"


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str
    title: str
    department: str
    description: str
    skills: str
    min_experience: Optional[float]
    education_required: str
    created_at: datetime


# --- Candidates ---
class CandidateCreate(BaseModel):
    external_id: str
    full_name: str = ""
    title: str = ""
    role_label: str = ""
    role_fine: str = "unknown"
    skills: str = ""
    raw_text: str = ""
    filename: str = ""
    storage_path: str = ""
    years_experience: Optional[float] = None
    highest_degree: str = ""
    certifications: str = ""
    education_lines: str = ""
    status: str = "new"


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str
    full_name: str
    title: str
    role_label: str
    role_fine: str
    skills: str
    filename: str
    storage_path: str
    years_experience: Optional[float]
    highest_degree: str
    certifications: str
    education_lines: str
    status: str
    created_at: datetime


class CandidateReadWithScores(CandidateRead):
    """Candidates list scoreboard only (cohort percentiles + mean job match)."""

    profile_percentile_score: float
    avg_job_match_score: float
    competition_score: float


# --- Stored rankings ---
class StoredRankingRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank_position: int
    cross_encoder_score: float
    sbert_similarity: float
    candidate_external_id: str
    candidate_name: str = ""
    candidate_title: str = ""
    candidate_role: str = ""
    years_experience: Optional[float] = None
    highest_degree: str = ""
    skills_summary: str = ""
    explanation: Optional[RankingExplanationOut] = None


class JobRankingsResponse(BaseModel):
    job_external_id: str
    rankings: List[StoredRankingRow]
    run_at: Optional[datetime] = None


class ResumeUploadResponse(BaseModel):
    """Result of POST /uploads/resume."""

    status: str
    text_len: int
    candidate: CandidateRead


# --- Resume ingestion (async, multi-source) ---
class IngestionCreateText(BaseModel):
    text: str = Field(..., min_length=20, description="Resume text or profile text captured from extension/OCR")
    source: str = Field("extension", max_length=32, description="extension|phone_ocr|api")
    filename: str = Field("resume.txt", max_length=1024)
    batch_id: Optional[UUID] = Field(None, description="Optional: group multiple ingestions under one batch")


class IngestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    source: str
    status: str
    filename: str
    content_type: str
    storage_path: str
    candidate_external_id: str
    error: str
    created_at: datetime
    updated_at: datetime


class IngestionBatchOut(BaseModel):
    batch_id: UUID
    accepted: List[IngestionOut]
    failed: List[IngestionOut]


class IngestionStatusOut(BaseModel):
    batch_id: UUID
    total: int
    queued: int
    processing: int
    done: int
    failed: int
    items: List[IngestionOut]


# --- Auth ---
class UserRegisterIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)


class RegisterStartResponse(BaseModel):
    status: str = "code_sent"


class VerifyEmailCodeIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    code: str = Field(..., min_length=4, max_length=12)


class VerifyEmailCodeResponse(BaseModel):
    status: str = "verified"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Human-in-the-loop (ranking feedback) ---
class HumanFeedbackCreate(BaseModel):
    job_external_id: str = Field(..., min_length=1, max_length=64)
    candidate_external_id: str = Field(..., min_length=1, max_length=64)
    action: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="e.g. selected, shortlisted, rejected, not_a_fit",
    )
    rank_position_shown: Optional[int] = Field(
        None,
        ge=1,
        description="1-based rank in the list the user saw when they acted",
    )
    model_score_at_feedback: Optional[float] = None
    notes: str = ""


class HumanFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_external_id: str
    candidate_external_id: str
    action: str
    rank_position_shown: Optional[int]
    model_score_at_feedback: Optional[float]
    created_at: datetime
