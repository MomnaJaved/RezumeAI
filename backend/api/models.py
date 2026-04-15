"""SQLAlchemy ORM models (PostgreSQL or SQLite)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    contact_person: Mapped[str] = mapped_column(String(256), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    company_name: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(24), default="active")  # active|inactive
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="client")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Matches job_id in jobs_enriched.csv (e.g. J001)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(512), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[str] = mapped_column(Text, default="")
    salary_range: Mapped[str] = mapped_column(String(128), default="")
    work_location: Mapped[str] = mapped_column(String(32), default="")  # on_site|remote
    job_type: Mapped[str] = mapped_column(String(32), default="")  # full_time|part_time
    recruitment_urgency: Mapped[str] = mapped_column(String(16), default="")  # high|medium|low
    preferred_onboarding_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    min_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    education_required: Mapped[str] = mapped_column(String(64), default="any")
    status: Mapped[str] = mapped_column(String(24), default="active")  # active|inactive
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped[Optional["Client"]] = relationship(back_populates="jobs")
    rankings: Mapped[list["JobCandidateRanking"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["JobAttachment"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobAttachment(Base):
    __tablename__ = "job_attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(2048), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    job: Mapped["Job"] = relationship(back_populates="attachments")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Matches candidate_id in candidates_enriched.csv
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Display name (from CV filename or manual); may differ from professional title below
    full_name: Mapped[str] = mapped_column(String(512), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    # Inferred role bucket: frontend | backend | fullstack (optional)
    role_label: Mapped[str] = mapped_column(String(128), default="")
    role_fine: Mapped[str] = mapped_column(String(64), default="unknown")
    skills: Mapped[str] = mapped_column(Text, default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(1024), default="")
    storage_path: Mapped[str] = mapped_column(String(2048), default="")
    years_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    highest_degree: Mapped[str] = mapped_column(String(256), default="")
    certifications: Mapped[str] = mapped_column(Text, default="")
    education_lines: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="new")
    # First email found in resume text at ingest (not in PII-stripped raw_text).
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    # Cached model-based best match vs jobs (0–100) to keep list/dashboard fast.
    best_job_match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_job_external_id: Mapped[str] = mapped_column(String(64), default="")
    # Semantic embedding (SBERT) of candidate text for fast shortlist (stored as raw float32 bytes).
    # Shape typically (384,) for all-MiniLM-L6-v2.
    embedding_sbert: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    rankings: Mapped[list["JobCandidateRanking"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class JobCandidateRanking(Base):
    """
    One row per (job, candidate) after a rank run.
    Re-run ranking replaces rows for that job (delete old then insert).
    """
    __tablename__ = "job_candidate_rankings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    rank_position: Mapped[int] = mapped_column(Integer)
    cross_encoder_score: Mapped[float] = mapped_column(Float)
    sbert_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    # Snapshot at rank time (for reports / FYP tables)
    candidate_name: Mapped[str] = mapped_column(String(512), default="")
    candidate_title: Mapped[str] = mapped_column(
        String(512), default=""
    )  # CV headline / professional title line
    candidate_role: Mapped[str] = mapped_column(String(128), default="")
    years_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    highest_degree: Mapped[str] = mapped_column(String(256), default="")
    skills_summary: Mapped[str] = mapped_column(Text, default="")
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    explanation_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped["Job"] = relationship(back_populates="rankings")
    candidate: Mapped["Candidate"] = relationship(back_populates="rankings")


class JobCandidateSbertScore(Base):
    """
    Stage-1 retrieval cache (SBERT cosine similarity) for (job, candidate).
    This table is used ONLY for shortlisting; never shown in UI.
    """

    __tablename__ = "job_candidate_sbert_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    cosine_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    rank_position: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class JobShortlistedCandidate(Base):
    """
    User-controlled shortlist per job.
    Cross-encoder runs ONLY on these candidates.
    """

    __tablename__ = "job_shortlisted_candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class JobApplicant(Base):
    """
    Single source of truth for applicant tracking per (job, candidate).
    """

    __tablename__ = "job_applicants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="new")  # new|screened|shortlisted|interviewed|hired
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_code_hash: Mapped[str] = mapped_column(String(256), default="")
    verification_code_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HumanRankingFeedback(Base):
    """
    Human action after viewing model-ranked candidates for a job.
    Use for offline retraining / evaluation — not live weight updates.
    """

    __tablename__ = "human_ranking_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    rank_position_shown: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_score_at_feedback: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResumeIngestion(Base):
    """
    Async ingestion record (bulk uploads, phone OCR images, browser extension text).
    Each row represents one input item and its processing state.
    """

    __tablename__ = "resume_ingestions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)

    # Source: bulk_upload | phone_ocr | extension | api
    source: Mapped[str] = mapped_column(String(32), default="api")
    status: Mapped[str] = mapped_column(String(24), default="queued")  # queued|processing|done|failed

    filename: Mapped[str] = mapped_column(String(1024), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="")
    storage_path: Mapped[str] = mapped_column(String(2048), default="")  # local path for raw bytes (optional)

    input_text: Mapped[str] = mapped_column(Text, default="")  # for extension text mode
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")

    candidate_external_id: Mapped[str] = mapped_column(String(64), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ActivityEvent(Base):
    """
    Append-only activity log for user-facing notifications (survives deletes).
    """

    __tablename__ = "activity_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64), default="info")
    message: Mapped[str] = mapped_column(String(512), default="")
    href: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
