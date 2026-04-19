"""Authenticated candidate-facing APIs (job discovery, applications, profile link)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Candidate, Client, Job, JobApplicant, User
from api.routers.auth import _get_auth_user

router = APIRouter(prefix="/candidate", tags=["candidate"])


def _require_candidate(request: Request, db: Session) -> User:
    u = _get_auth_user(request, db)
    role = (getattr(u, "account_role", None) or "recruiter").strip().lower()
    if role != "candidate":
        raise HTTPException(status_code=403, detail="Candidate account required")
    return u


def _linked_candidate(db: Session, user: User) -> Optional[Candidate]:
    return db.query(Candidate).filter(Candidate.user_id == user.id).first()


@router.get("/me")
def candidate_me(request: Request, db: Session = Depends(get_db)):
    """Linked pool candidate row for this account (same data recruiters see)."""
    user = _require_candidate(request, db)
    c = _linked_candidate(db, user)
    if not c:
        return {
            "linked": False,
            "candidate_id": None,
            "external_id": None,
            "full_name": user.full_name or "",
            "email": user.email,
        }
    return {
        "linked": True,
        "candidate_id": str(c.id),
        "external_id": c.external_id,
        "full_name": (c.full_name or "").strip(),
        "title": (c.title or "").strip(),
        "status": (c.status or "").strip(),
        "best_job_match_score": c.best_job_match_score,
        "best_job_external_id": (c.best_job_external_id or "").strip(),
        "email": user.email,
    }


@router.get("/jobs")
def list_open_jobs(
    request: Request,
    db: Session = Depends(get_db),
    role_q: str = Query("", description="Search title / skills / department"),
    work_location: str = Query("", description="Filter work_location (e.g. remote, on_site)"),
    country: str = Query("", description="Reserved: substring match in description (no dedicated country field yet)"),
    city: str = Query("", description="Reserved: substring match in description"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    _require_candidate(request, db)
    base = db.query(Job).filter(func.lower(Job.status) == "active")
    rq = (role_q or "").strip()
    if rq:
        like = f"%{rq}%"
        base = base.filter(
            or_(Job.title.ilike(like), Job.skills.ilike(like), Job.department.ilike(like), Job.description.ilike(like))
        )
    wl = (work_location or "").strip().lower()
    if wl:
        base = base.filter(func.lower(Job.work_location) == wl)
    co = (country or "").strip()
    if co:
        like = f"%{co}%"
        base = base.filter(Job.description.ilike(like))
    ci = (city or "").strip()
    if ci:
        like = f"%{ci}%"
        base = base.filter(Job.description.ilike(like))
    total = int(base.count())
    rows = base.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()
    out: list[dict[str, Any]] = []
    for j in rows:
        cl_name = ""
        if j.client_id:
            cl = db.query(Client).filter(Client.id == j.client_id).first()
            if cl:
                cl_name = (cl.company_name or cl.name or "").strip()
        out.append(
            {
                "id": str(j.id),
                "external_id": j.external_id,
                "title": j.title or "",
                "department": j.department or "",
                "work_location": j.work_location or "",
                "job_type": j.job_type or "",
                "salary_range": j.salary_range or "",
                "client_display": cl_name,
                "created_at": j.created_at.isoformat() if j.created_at else "",
            }
        )
    return {"total": total, "items": out}


@router.post("/jobs/{external_id}/apply")
def apply_to_job(request: Request, external_id: str, db: Session = Depends(get_db)):
    user = _require_candidate(request, db)
    cand = _linked_candidate(db, user)
    if not cand:
        raise HTTPException(
            status_code=400,
            detail="Upload your resume first to join the candidate pool and apply to jobs.",
        )
    job = db.query(Job).filter(Job.external_id == external_id.strip()).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if (job.status or "").strip().lower() != "active":
        raise HTTPException(status_code=400, detail="This job is not accepting applications")
    now = datetime.utcnow()
    app = (
        db.query(JobApplicant)
        .filter(JobApplicant.job_id == job.id, JobApplicant.candidate_id == cand.id)
        .first()
    )
    if app:
        return {"status": "already_applied", "applicant_status": app.status}
    db.add(JobApplicant(job_id=job.id, candidate_id=cand.id, status="new", updated_at=now))
    db.commit()
    return {"status": "applied", "applicant_status": "new"}


@router.get("/applications")
def my_applications(request: Request, db: Session = Depends(get_db)):
    user = _require_candidate(request, db)
    cand = _linked_candidate(db, user)
    if not cand:
        return {"items": []}
    rows = (
        db.query(JobApplicant, Job, Client)
        .join(Job, Job.id == JobApplicant.job_id)
        .outerjoin(Client, Client.id == Job.client_id)
        .filter(JobApplicant.candidate_id == cand.id)
        .order_by(JobApplicant.updated_at.desc())
        .all()
    )
    items: list[dict[str, Any]] = []
    for app, job, cl in rows:
        company = (cl.company_name or cl.name or "").strip() if cl else ""
        items.append(
            {
                "job_external_id": job.external_id,
                "job_title": (job.title or "").strip(),
                "company": company,
                "status": (app.status or "new").strip(),
                "updated_at": app.updated_at.isoformat() if app.updated_at else "",
            }
        )
    return {"items": items}
