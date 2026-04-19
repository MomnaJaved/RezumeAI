"""Effective applicant / pipeline status (e.g. auto-expire literal 'new' after N days)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Literal "new" is shown as the next pipeline stage after this many days since candidate creation.
NEW_APPLICANT_TTL_DAYS = 7
NEW_CANDIDATE_TTL_DAYS = 7

# Canonical pipeline status values — the ONLY values accepted by any status-write endpoint.
# AI scoring (SBERT, cross-encoder, ranking) must NEVER write to this field.
STORAGE_APPLICANT_STATUSES = frozenset(
    {
        "new",
        "screened",
        "shortlisted",
        "interviewing",
        "selected",
        "hired",
        "rejected",
    }
)

# Legacy values that may exist in old data — mapped on read and migrated in DB.
_LEGACY_STATUS_MAP: dict[str, str] = {
    "interview": "interviewing",
    "interviewed": "interviewing",
    "declined": "rejected",
    "reviewed": "screened",
}


def effective_applicant_status(stored: str | None, candidate_created_at: datetime | None) -> str:
    """
    JobApplicant pipeline: stored 'new' ages out to 'screened' for display/counts once the
    candidate profile is older than NEW_APPLICANT_TTL_DAYS (query-time, no DB write).
    Also resolves legacy aliases to canonical values.
    """
    s = _normalize_status(stored)
    if s != "new":
        return s
    if candidate_created_at is None:
        return s
    if datetime.utcnow() - candidate_created_at >= timedelta(days=NEW_APPLICANT_TTL_DAYS):
        return "screened"
    return "new"


def effective_candidate_status(stored: str | None, candidate_created_at: datetime | None) -> str:
    """Global Candidate.status: same TTL rule for literal 'new'. Also resolves legacy aliases."""
    s = _normalize_status(stored)
    if s != "new":
        return s
    if candidate_created_at is None:
        return s
    if datetime.utcnow() - candidate_created_at >= timedelta(days=NEW_CANDIDATE_TTL_DAYS):
        return "screened"
    return "new"


def _normalize_status(s: str | None) -> str:
    """Resolve legacy aliases to the canonical 7-value set."""
    raw = (s or "new").strip().lower()
    return _LEGACY_STATUS_MAP.get(raw, raw)


def stage_bucket_for_dashboard(stored: str | None) -> str:
    """Normalize status to a dashboard bucket using the canonical 7-value set."""
    s = _normalize_status(stored)
    if s == "hired":
        return "hired"
    if s == "rejected":
        return "rejected"
    if s == "interviewing":
        return "interviewing"
    if s in ("shortlisted", "selected"):
        return "shortlisted"
    if s == "screened":
        return "screened"
    return "new"


def applicant_tracker_counts(
    status_created_pairs: list[tuple[str | None, datetime | None]],
) -> dict[str, int]:
    """
    Roll up JobApplicant rows to UI buckets after applying effective_applicant_status per row.
    """
    eff = Counter()
    for st, cat in status_created_pairs:
        e = effective_applicant_status(st, cat)
        eff[e] += 1

    def pick(*keys: str) -> int:
        return sum(int(eff.get(k, 0)) for k in keys)

    return {
        "total": sum(eff.values()),
        "new": pick("new"),
        "screened": pick("screened"),
        "shortlisted": pick("shortlisted", "selected"),
        "interviewing": pick("interviewing"),
        "hired": pick("hired"),
        "rejected": pick("rejected"),
    }


# Priority order for collapsing multiple job-application statuses into one candidate status.
_STATUS_PRIORITY: dict[str, int] = {
    "hired": 7,
    "rejected": 6,
    "declined": 6,
    "interviewed": 5,
    "interviewing": 5,
    "interview": 5,
    "shortlisted": 4,
    "selected": 4,
    "screened": 3,
    "reviewed": 3,
    "new": 1,
}


def sync_candidate_status_from_applicants(db: "Session", candidate: "object") -> None:
    """
    Update candidates.status to the highest-priority status across all job_applicants rows.
    Call this immediately after updating any job_applicants.status so the candidates page,
    candidate detail, and dashboard all stay in sync.

    Does NOT commit — caller is responsible for db.commit().
    """
    from api.models import JobApplicant

    rows = (
        db.query(JobApplicant.status)
        .filter(JobApplicant.candidate_id == candidate.id)
        .all()
    )
    if not rows:
        return
    best = max(
        ((r.status or "new").strip().lower() for r in rows),
        key=lambda s: _STATUS_PRIORITY.get(s, 0),
    )
    candidate.status = best


def global_applicant_status_created_pairs(db: "Session") -> list[tuple[str | None, datetime | None]]:
    """
    Rows that drive the **global** applicant pipeline (dashboard + /analytics/applicant-stats):

    - Every `job_applicants` row (per job application), joined to the candidate's `created_at`
      for the literal-`new` TTL rule.
    - Plus each `candidates` row that has **no** `job_applicants` row, using `candidates.status`
      (edited on the candidate profile) so those profiles are not invisible on the dashboard.
    """
    from sqlalchemy import exists

    from api.models import Candidate, JobApplicant

    job_rows = (
        db.query(JobApplicant.status, Candidate.created_at)
        .join(Candidate, Candidate.id == JobApplicant.candidate_id)
        .all()
    )
    has_app = exists().where(JobApplicant.candidate_id == Candidate.id)
    orphan_rows = db.query(Candidate.status, Candidate.created_at).filter(~has_app).all()
    pairs: list[tuple[str | None, datetime | None]] = [(str(st or "new"), cat) for st, cat in job_rows]
    pairs.extend([(str(st or "new"), cat) for st, cat in orphan_rows])
    return pairs


def applicant_pairs_for_job_ids(db: "Session", job_ids: list[UUID]) -> list[tuple[str | None, datetime | None]]:
    """Applicant rows limited to specific jobs (e.g. reports filters)."""
    from api.models import Candidate, JobApplicant

    if not job_ids:
        return []
    job_rows = (
        db.query(JobApplicant.status, Candidate.created_at)
        .join(Candidate, Candidate.id == JobApplicant.candidate_id)
        .filter(JobApplicant.job_id.in_(job_ids))
        .all()
    )
    return [(str(st or "new"), cat) for st, cat in job_rows]


def recruiter_applicant_status_created_pairs(db: "Session", workspace_id: UUID) -> list[tuple[str | None, datetime | None]]:
    """
    Applicant pipeline rows for **one recruiter workspace**: applications only to jobs in that workspace.

    Does not include global "orphan" candidates (no job_applicant row) — those are pool-wide,
    not attributable to a single workspace's jobs.
    """
    from api.models import Candidate, Job, JobApplicant

    job_rows = (
        db.query(JobApplicant.status, Candidate.created_at)
        .join(Candidate, Candidate.id == JobApplicant.candidate_id)
        .join(Job, Job.id == JobApplicant.job_id)
        .filter(Job.workspace_id == workspace_id)
        .all()
    )
    return [(str(st or "new"), cat) for st, cat in job_rows]
