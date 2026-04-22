"""Pydantic schemas for API requests and responses."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from api.services.candidate_title_display import polish_candidate_title, polish_role_fine_display
from src.parsing.candidate_title_resolve import display_title_for_candidate_row


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
    total_skill_coverage: float = 0.0
    critical_skill_coverage: float = 0.0
    experience_match: float
    education_match: float
    heuristic_weak_score: float
    missing_skills: List[str]
    missing_critical_skills: List[str] = []
    cross_encoder_score_raw: float = 0.0
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
class ClientCreate(BaseModel):
    name: str
    contact_person: str = ""
    email: str = ""
    company_name: str = ""
    status: str = "active"


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    contact_person: str = ""
    email: str = ""
    company_name: str = ""
    active_jobs: int = 0
    status: str
    created_at: datetime


class ClientUpdate(BaseModel):
    """Partial update; omit fields to leave unchanged."""

    name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    company_name: Optional[str] = None
    status: Optional[str] = None


class JobCreate(BaseModel):
    external_id: str = ""
    client_id: Optional[UUID] = None
    title: str = ""
    department: str = ""
    description: str = ""
    skills: str = ""
    salary_range: str = ""
    work_location: str = ""
    job_type: str = ""
    recruitment_urgency: str = ""
    preferred_onboarding_date: Optional[datetime] = None
    min_experience: Optional[float] = None
    education_required: str = "any"
    status: str = "active"


class JobUpdate(BaseModel):
    """Partial update; omit fields to leave unchanged."""

    title: Optional[str] = None
    client_id: Optional[UUID] = None
    department: Optional[str] = None
    description: Optional[str] = None
    skills: Optional[str] = None
    salary_range: Optional[str] = None
    work_location: Optional[str] = None
    job_type: Optional[str] = None
    recruitment_urgency: Optional[str] = None
    preferred_onboarding_date: Optional[datetime] = None
    min_experience: Optional[float] = None
    education_required: Optional[str] = None
    status: Optional[str] = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str
    client_id: Optional[UUID] = None
    client_name: str = ""
    title: str
    department: str
    description: str
    skills: str
    salary_range: str = ""
    work_location: str = ""
    job_type: str = ""
    recruitment_urgency: str = ""
    preferred_onboarding_date: Optional[datetime] = None
    min_experience: Optional[float]
    education_required: str
    status: str
    created_at: datetime
    created_by_user_id: Optional[UUID] = None
    workspace_id: Optional[UUID] = None


# --- Job attachments ---
class JobAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_external_id: str
    filename: str
    content_type: str
    size_bytes: int
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
    contact_email: str = ""


class CandidateUpdate(BaseModel):
    """Partial update; omit fields to leave unchanged."""

    full_name: Optional[str] = None
    title: Optional[str] = None
    role_label: Optional[str] = None
    role_fine: Optional[str] = None
    skills: Optional[str] = None
    years_experience: Optional[float] = None
    highest_degree: Optional[str] = None
    certifications: Optional[str] = None
    education_lines: Optional[str] = None
    status: Optional[str] = None
    contact_email: Optional[str] = None


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
    """Query-time status for literal `new` (ages to screened after 7 days from created_at)."""
    status_effective: str = "new"
    """When title is Fresher, optional skills-inferred role label for transparency."""
    skills_role_hint: Optional[str] = None
    contact_email: str = ""
    created_at: datetime
    # Cached ATS match score fields (optional; present when computed).
    best_job_match_score: Optional[float] = None
    best_job_external_id: Optional[str] = None
    # Enriched from best_job_external_id for list/detail UX (optional).
    best_job_title: Optional[str] = None
    best_job_department: Optional[str] = None
    best_job_client_name: Optional[str] = None
    best_job_client_company: Optional[str] = None
    best_job_client_contact: Optional[str] = None
    best_job_client_email: Optional[str] = None
    # Pool type: True = public (portal applicant), False = private (recruiter upload).
    is_public: bool = False

    @field_serializer("title")
    def _ser_title(self, v: str) -> str:
        # Polish can strip some inferred/minimal strings to empty; never return a blank headline.
        p = polish_candidate_title(v)
        if p:
            return p
        t = (v or "").strip()
        if t:
            return t
        fb = display_title_for_candidate_row(
            title="",
            skills=self.skills or "",
            years_experience=self.years_experience,
            role_label=self.role_label or "",
            raw_text="",
        )
        return (fb or "").strip() or "Professional"

    @field_serializer("role_label")
    def _ser_role_label(self, v: str) -> str:
        return polish_candidate_title(v)

    @field_serializer("role_fine")
    def _ser_role_fine(self, v: str) -> str:
        return polish_role_fine_display(v)


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
    top_candidate_insight: Optional[str] = Field(
        default=None,
        description="Executive narrative for why rank #1 leads the shortlist (job/candidate/explanation data).",
    )


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
    account_role: str = Field(default="recruiter", description="recruiter | candidate")


class LoginCredentialsIn(BaseModel):
    """Sign-in body: allow short passwords so the API can return 401 instead of 422."""

    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


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
    account_role: Optional[str] = None


class LoginResult(BaseModel):
    """Password step: either a token, or an OTP challenge for 2FA users."""

    access_token: Optional[str] = None
    token_type: str = "bearer"
    requires_otp: bool = False
    otp_challenge_id: Optional[str] = None
    account_role: Optional[str] = None


class LoginOtpCompleteIn(BaseModel):
    challenge_id: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=4, max_length=12)


class UserSessionOut(BaseModel):
    id: str
    device_label: str
    location_label: str
    ip_address: str
    created_at: str
    last_seen_at: str
    is_current: bool


class UserProfileOut(BaseModel):
    id: str
    email: str
    full_name: str
    phone: str
    address: str
    company: str
    available_hours: str
    role_label: str
    avatar_data: Optional[str] = None
    two_factor_enabled: bool = False
    account_role: str = "recruiter"
    workspace_id: Optional[str] = None


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    company: Optional[str] = None
    available_hours: Optional[str] = None
    role_label: Optional[str] = None
    avatar_data: Optional[str] = None
    two_factor_enabled: Optional[bool] = None


class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class DeleteAccountIn(BaseModel):
    """Confirm account deletion with the current password."""

    password: str = Field(..., min_length=1, max_length=256)


class ForgotPasswordIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)


class ForgotPasswordResponse(BaseModel):
    status: str = "ok"


class ResetPasswordIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    code: str = Field(..., min_length=4, max_length=12)
    new_password: str = Field(..., min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    status: str = "password_reset"


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


# --- Inbox (activity + messages + read state) ---
class InboxItemOut(BaseModel):
    id: str
    kind: str
    message: str
    at: str
    href: Optional[str] = None
    read: bool
    tabs: List[str] = Field(default_factory=list)
    direct: bool = False
    sender_email: Optional[str] = None
    direction: Optional[str] = None  # in | out
    peer_email: Optional[str] = None
    chat_scope: Optional[str] = None
    peer_display_name: Optional[str] = None
    peer_profile_path: Optional[str] = None


class InboxIdsBody(BaseModel):
    ids: List[str] = Field(default_factory=list)


class InboxTabBody(BaseModel):
    tab: str = Field(default="all", description="all | alerts | candidates")


class InboxSendIn(BaseModel):
    to_email: str = Field(..., min_length=3, max_length=320)
    body: str = Field(..., min_length=1, max_length=20000)
    subject: str = Field(default="", max_length=512)
    chat_scope: str = Field(default="general", description="general | candidates | clients")


class InboxMarkResult(BaseModel):
    updated: int


class InboxThreadDeleteIn(BaseModel):
    peer_email: str = Field(..., min_length=3, max_length=320)
    chat_scope: str = Field(..., description="general | candidates | clients")


class InboxThreadDeleteResult(BaseModel):
    deleted: int


class InboxMessageDeleteIn(BaseModel):
    mode: str = Field(..., description="everyone | me")


# --- OCR ---
class OcrParsedFields(BaseModel):
    full_name: str = ""
    contact_email: str = ""
    title: str = ""
    role_label: str = ""
    skills: str = ""
    years_experience: Optional[float] = None
    highest_degree: str = ""
    education_lines: str = ""
    certifications: str = ""


class OcrParseResponse(BaseModel):
    raw_text: str
    parsed_fields: OcrParsedFields
    filename: str
    text_len: int
