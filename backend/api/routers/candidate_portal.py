"""Authenticated candidate-facing APIs (job discovery, applications, profile link)."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional
import uuid as uuid_lib
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from api.database import get_db, engine
from api.models import Candidate, Client, Job, JobApplicant, JobCandidateRanking, User
from api.routers.auth import _get_auth_user

_log = logging.getLogger("rezume.api")

router = APIRouter(prefix="/candidate", tags=["candidate"])

# Minimal practical check (not full RFC 5322); empty string clears the field.
_RE_CONTACT_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _require_candidate(request: Request, db: Session) -> User:
    u = _get_auth_user(request, db)
    role = (getattr(u, "account_role", None) or "recruiter").strip().lower()
    if role != "candidate":
        raise HTTPException(status_code=403, detail="Candidate account required")
    return u


def _linked_candidate(db: Session, user: User) -> Optional[Candidate]:
    return db.query(Candidate).filter(Candidate.user_id == user.id).first()


def _uuid_key(val: Any) -> UUID:
    """Normalize ORM/driver UUID values for consistent set membership."""
    if isinstance(val, UUID):
        return val
    return UUID(str(val))


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
    user = _require_candidate(request, db)
    cand = _linked_candidate(db, user)
    applied_job_ids: set[UUID] = set()
    if cand:
        applied_job_ids = {
            _uuid_key(jid)
            for (jid,) in db.query(JobApplicant.job_id).filter(JobApplicant.candidate_id == cand.id).all()
            if jid is not None
        }

    # Only jobs tied to a recruiter workspace — same scope as GET /jobs/page for
    # recruiters, so every application is visible to the posting tenant.
    base = db.query(Job).filter(func.lower(Job.status) == "active", Job.workspace_id.isnot(None))
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
                "applied": _uuid_key(j.id) in applied_job_ids,
            }
        )
    return {"total": total, "items": out}


@router.post("/jobs/{external_id}/apply")
def apply_to_job(
    request: Request,
    external_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
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
    # Must match jobs visible in list_open_jobs: only tenant-scoped postings so the
    # owning recruiter sees the applicant in their workspace (legacy rows with NULL
    # workspace_id are excluded from recruiter job lists).
    if getattr(job, "workspace_id", None) is None:
        raise HTTPException(status_code=400, detail="This job is not open for applications.")
    if (job.status or "").strip().lower() != "active":
        raise HTTPException(status_code=400, detail="This job is not accepting applications")
    now = datetime.utcnow()
    app = (
        db.query(JobApplicant)
        .filter(JobApplicant.job_id == job.id, JobApplicant.candidate_id == cand.id)
        .first()
    )
    # Any candidate who reaches this point via the portal is a public candidate.
    cand.is_public = True

    # Log if workspace_id mismatch so we can spot cross-workspace applications in
    # the terminal — the SBERT purge historically deleted these; now protected by
    # the is_public / user_id guard in sbert_cache.refresh_sbert_for_job.
    cand_ws = getattr(cand, "workspace_id", None)
    job_ws = getattr(job, "workspace_id", None)
    if cand_ws is not None and job_ws is not None and cand_ws != job_ws:
        _log.info(
            "Cross-workspace apply: candidate %s (ws=%s) → job %s (ws=%s). "
            "Application will be preserved (portal candidate).",
            cand.external_id,
            cand_ws,
            job.external_id,
            job_ws,
        )

    if app:
        # Already in the pipeline (recruiter added them). Mark public and return
        # success — never show the candidate a confusing "already applied" message.
        db.commit()
        return {"status": "applied", "applicant_status": app.status}

    db.add(JobApplicant(job_id=job.id, candidate_id=cand.id, status="new", updated_at=now))
    db.commit()

    # Re-score this candidate against the job they just applied to so the
    # recruiter sees a score computed for *this* job, not a stale value from
    # a different job/recruiter. Runs in the background so the apply response
    # is instant for the candidate.
    job_id = job.id
    background_tasks.add_task(_rescore_job_after_apply, job_id)

    return {"status": "applied", "applicant_status": "new"}


def _rescore_job_after_apply(job_id) -> None:
    """Background task: refresh SBERT shortlist for the job a candidate just applied to."""
    try:
        from api.services.sbert_cache import refresh_sbert_for_job_id
        refresh_sbert_for_job_id(engine, job_id, top_k=200)
    except Exception as e:
        _log.warning("Post-apply SBERT refresh failed for job %s: %s", job_id, e)


def _refresh_candidate_embedding(cand_id: uuid_lib.UUID) -> None:
    """Background task: recompute SBERT embedding after profile edit."""
    try:
        from sqlalchemy.orm import sessionmaker
        from api.services.sbert_cache import ensure_candidate_embedding

        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        try:
            cand = db.query(Candidate).filter(Candidate.id == cand_id).first()
            if cand:
                ensure_candidate_embedding(db, cand)
        finally:
            db.close()
    except Exception as e:
        _log.warning("Embedding refresh failed for candidate %s: %s", cand_id, e)


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

    # Bulk-fetch ranking rows for this candidate so we avoid N+1 queries.
    job_ids = [job.id for _, job, _ in rows]
    ranking_map: dict[Any, Any] = {}
    if job_ids:
        ranking_rows = (
            db.query(JobCandidateRanking)
            .filter(
                JobCandidateRanking.candidate_id == cand.id,
                JobCandidateRanking.job_id.in_(job_ids),
            )
            .all()
        )
        # For each job keep the ranking whose workspace_id matches the job's
        # own workspace (the recruiter who owns the job ran the scoring).
        # Fall back to any available ranking if no workspace-matched one exists.
        for r in ranking_rows:
            jid = r.job_id
            if jid not in ranking_map:
                ranking_map[jid] = r
            else:
                # Prefer the workspace-matched ranking — resolved below after
                # we have the job objects.
                existing = ranking_map[jid]
                # Keep higher-priority ranking: workspace match beats non-match,
                # then prefer higher score.
                if (r.cross_encoder_score or 0) > (existing.cross_encoder_score or 0):
                    ranking_map[jid] = r

    # Re-prefer workspace-matched rankings now that we have job objects.
    job_ws_map = {job.id: getattr(job, "workspace_id", None) for _, job, _ in rows}
    # Second pass: pick workspace-matched row if available.
    ws_ranking_map: dict[Any, Any] = {}
    for r in (ranking_rows if job_ids else []):
        jid = r.job_id
        r_ws = getattr(r, "workspace_id", None)
        job_ws = job_ws_map.get(jid)
        if job_ws is not None and r_ws == job_ws:
            # This ranking was made by the job's own recruiter — highest priority.
            if jid not in ws_ranking_map or (r.cross_encoder_score or 0) > (ws_ranking_map[jid].cross_encoder_score or 0):
                ws_ranking_map[jid] = r
    # Merge: workspace-matched rankings override the fallback map.
    ranking_map.update(ws_ranking_map)

    items: list[dict[str, Any]] = []
    for app, job, cl in rows:
        company = (cl.company_name or cl.name or "").strip() if cl else ""
        rnk = ranking_map.get(job.id)
        raw_score = float(rnk.cross_encoder_score or 0.0) if rnk else None
        # Convert 0-1 → 0-100 and round to one decimal place for readability.
        match_score = round(raw_score * 100.0, 1) if raw_score is not None else None
        rank_position = int(rnk.rank_position) if rnk and rnk.rank_position is not None else None
        items.append(
            {
                "job_external_id": job.external_id,
                "job_title": (job.title or "").strip(),
                "company": company,
                "status": (app.status or "new").strip(),
                "updated_at": app.updated_at.isoformat() if app.updated_at else "",
                "rank_position": rank_position,
                "match_score": match_score,
            }
        )
    return {"items": items}


@router.patch("/profile")
def update_candidate_profile(
    request: Request,
    body: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Let the candidate update their own profile details (name, title, skills, etc.).
    Changes are immediately visible to any recruiter viewing this candidate.
    """
    user = _require_candidate(request, db)
    cand = _linked_candidate(db, user)
    if not cand:
        raise HTTPException(status_code=404, detail="No profile linked. Upload a resume first.")

    changed = False
    embedding_dirty = False

    def _set(field: str, value: Any, *, strip: bool = True, touches_embedding: bool = False) -> None:
        nonlocal changed, embedding_dirty
        if field not in body:
            return
        v = (str(value or "").strip()) if strip else value
        if getattr(cand, field, None) != v:
            setattr(cand, field, v)
            changed = True
            if touches_embedding:
                embedding_dirty = True

    _set("full_name", body.get("full_name"))
    _set("title", body.get("title"), touches_embedding=True)
    _set("skills", body.get("skills"), touches_embedding=True)

    if "contact_email" in body:
        em = str(body.get("contact_email") or "").strip()[:320]
        if em and not _RE_CONTACT_EMAIL.match(em):
            raise HTTPException(status_code=422, detail="Invalid email address.")
        if cand.contact_email != em:
            cand.contact_email = em
            changed = True

    yoe = body.get("years_experience")
    if "years_experience" in body:
        try:
            parsed_yoe = int(yoe) if yoe not in (None, "") else None
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="years_experience must be a whole number.")
        if cand.years_experience != parsed_yoe:
            cand.years_experience = parsed_yoe
            changed = True
            embedding_dirty = True

    if not changed:
        return {"status": "no_change"}

    if embedding_dirty:
        # Skill/title/YoE edits affect SBERT résumé text; contact_email does not.
        cand.embedding_sbert = None
    db.commit()
    db.refresh(cand)

    if embedding_dirty:
        background_tasks.add_task(_refresh_candidate_embedding, cand.id)

    _log.info("Candidate profile updated by user %s (candidate %s)", user.id, cand.external_id)
    return {"status": "updated"}
