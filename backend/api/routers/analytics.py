from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import JobApplicant

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/applicant-stats")
def applicant_stats(db: Session = Depends(get_db)):
    """
    Global applicant tracker counts across all jobs.
    Single source of truth: job_applicants table only.
    """
    rows = (
        db.query(JobApplicant.status, func.count(JobApplicant.id))
        .group_by(JobApplicant.status)
        .all()
    )
    counts = {str(st or "new").strip().lower(): int(n or 0) for st, n in rows}
    # Normalize common keys
    out = {
        "total": int(sum(counts.values())),
        "new": int(counts.get("new", 0)),
        "screened": int(counts.get("screened", 0)),
        "shortlisted": int(counts.get("shortlisted", 0)),
        "interviewed": int(counts.get("interviewed", 0)),
        "hired": int(counts.get("hired", 0)),
    }
    return out

