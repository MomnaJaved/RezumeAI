from __future__ import annotations

import re
from uuid import UUID

import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import require_user_if_auth_enabled
from api.errors import RezumeAPIError
from datetime import datetime

from sqlalchemy import func

from api.models import Candidate, Client, Job, JobApplicant, JobAttachment, JobCandidateRanking
from api.schemas import JobAttachmentRead, JobCreate, JobRead, JobUpdate, StoredRankingRow
from api.services.resume_ingest import MAX_UPLOAD_BYTES, _storage_root  # reuse upload dir helper
from api.database import engine

router = APIRouter(prefix="/jobs", tags=["jobs"])

_JOB_ID_RE = re.compile(r"^J(\d+)$", re.IGNORECASE)
_JOB_STATUSES = {"active", "on_hold", "completed", "cancelled"}

_APPLICANT_STATUSES = {"new", "screened", "shortlisted", "interviewed", "hired"}


def _norm_job_status(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s == "inactive":
        return "on_hold"
    if s == "on-hold":
        return "on_hold"
    return s


def _next_job_external_id(db: Session) -> str:
    """
    Generate the next job external id (J001, J002, ...).
    """
    # Fetch recent IDs only (fast) and parse numeric suffix.
    rows = db.query(Job.external_id).order_by(Job.created_at.desc()).limit(500).all()
    best = 0
    for (ext,) in rows:
        m = _JOB_ID_RE.match((ext or "").strip())
        if not m:
            continue
        try:
            best = max(best, int(m.group(1)))
        except ValueError:
            continue
    n = best + 1
    # Ensure uniqueness in case of gaps or mixed IDs.
    for _ in range(1000):
        ext = f"J{n:03d}"
        exists = db.query(Job).filter(Job.external_id == ext).first()
        if not exists:
            return ext
        n += 1
    raise HTTPException(status_code=500, detail="Could not generate a unique job id")


def _job_read(job: Job) -> JobRead:
    jr = JobRead.model_validate(job)
    jr.client_name = (job.client.name if getattr(job, "client", None) else "") or ""
    return jr


def _safe_filename(name: str) -> str:
    return "".join(c if (c.isalnum() or c in ("-", "_", ".", " ")) else "_" for c in (name or "file")).strip()[:160]


_ALLOWED_ATTACH_CT = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/octet-stream",
}


@router.get("", response_model=list[JobRead])
def list_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit)
    return [_job_read(j) for j in q.all()]


@router.get("/page")
def list_jobs_page(
    skip: int = 0,
    limit: int = Query(50, ge=1, le=100),
    q: str = "",
    status: str = "",
    client_id: str = "",
    sort: str = "created_desc",
    db: Session = Depends(get_db),
):
    """
    Server-side jobs listing with filters.
    Returns: { total, items }.
    """
    needle = (q or "").strip()
    st = (status or "").strip().lower()
    cid = (client_id or "").strip()
    srt = (sort or "created_desc").strip().lower()

    base = db.query(Job)
    if needle:
        like = f"%{needle}%"
        base = base.filter(
            or_(
                Job.external_id.ilike(like),
                Job.title.ilike(like),
                Job.department.ilike(like),
                Job.skills.ilike(like),
                Job.description.ilike(like),
            )
        )
    if st:
        stn = _norm_job_status(st)
        if stn not in _JOB_STATUSES:
            raise HTTPException(status_code=422, detail="status must be one of: active, on_hold, completed, cancelled")
        if stn == "on_hold":
            base = base.filter(Job.status.in_(["on_hold", "inactive"]))
        else:
            base = base.filter(Job.status == stn)
    if cid:
        base = base.filter(Job.client_id == cid)

    total = int(base.count())

    if srt == "created_asc":
        base = base.order_by(Job.created_at.asc())
    elif srt == "title_asc":
        base = base.order_by(Job.title.asc())
    elif srt == "title_desc":
        base = base.order_by(Job.title.desc())
    else:
        base = base.order_by(Job.created_at.desc())

    rows = base.offset(max(0, int(skip or 0))).limit(int(limit)).all()
    client_ids = {str(j.client_id) for j in rows if j.client_id}
    clients: dict[str, str] = {}
    if client_ids:
        for c in db.query(Client).filter(Client.id.in_(list(client_ids))).all():
            clients[str(c.id)] = c.name

    items = []
    for j in rows:
        jr = JobRead.model_validate(j)
        jr.client_name = clients.get(str(j.client_id), "") if j.client_id else ""
        items.append(jr)
    return {"total": total, "items": items}


@router.get("/{external_id}/candidates")
def candidates_for_job(external_id: str, limit: int = 200, db: Session = Depends(get_db)):
    """
    Ranked candidates for a job (stored matches), ordered by rank/score.
    Uses external job id (e.g., J001) to match existing UI + data model.
    """
    job = db.query(Job).filter(Job.external_id == external_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    lim = max(1, min(int(limit or 200), 500))
    rows = (
        db.query(JobCandidateRanking)
        .filter(JobCandidateRanking.job_id == job.id)
        .order_by(JobCandidateRanking.rank_position.asc(), JobCandidateRanking.cross_encoder_score.desc())
        .limit(lim)
        .all()
    )
    items = []
    for r in rows:
        items.append(
            StoredRankingRow(
                rank_position=r.rank_position,
                cross_encoder_score=r.cross_encoder_score,
                sbert_similarity=r.sbert_similarity,
                candidate_external_id=(r.candidate.external_id if getattr(r, "candidate", None) else ""),
                candidate_name=r.candidate_name,
                candidate_title=r.candidate_title,
                candidate_role=r.candidate_role,
                years_experience=r.years_experience,
                highest_degree=r.highest_degree,
                skills_summary=r.skills_summary,
                explanation=None,
            )
        )
    return {"job_external_id": job.external_id, "items": items}


@router.get("/by-external/{external_id}", response_model=JobRead)
def get_job_by_external_id(external_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.external_id == external_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_read(job)


@router.get("/{job_uuid}", response_model=JobRead)
def get_job(job_uuid: UUID, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_read(job)


@router.post("", response_model=JobRead, status_code=201)
def create_job(body: JobCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    ext = (body.external_id or "").strip().upper()
    if not ext:
        ext = _next_job_external_id(db)
    existing = db.query(Job).filter(Job.external_id == ext).first()
    if existing:
        raise HTTPException(status_code=409, detail="Job with this external_id already exists")
    job = Job(
        external_id=ext,
        client_id=body.client_id,
        title=body.title,
        department=body.department,
        description=body.description,
        skills=body.skills,
        salary_range=(body.salary_range or "").strip(),
        work_location=(body.work_location or "").strip().lower(),
        job_type=(body.job_type or "").strip().lower(),
        recruitment_urgency=(body.recruitment_urgency or "").strip().lower(),
        preferred_onboarding_date=body.preferred_onboarding_date,
        min_experience=body.min_experience,
        education_required=body.education_required or "any",
        status=_norm_job_status(body.status or "active"),
    )
    if job.status not in _JOB_STATUSES:
        raise HTTPException(status_code=422, detail="status must be one of: active, on_hold, completed, cancelled")
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        from api.services.sbert_cache import refresh_sbert_for_job_id

        # SBERT stage-1 runs in background; cross-encoder is user-triggered.
        background.add_task(refresh_sbert_for_job_id, engine, job.id, 200)
    except Exception:
        # Best-effort; do not block job creation.
        pass
    return _job_read(job)


@router.patch("/by-external/{external_id}", response_model=JobRead)
def update_job_by_external_id(external_id: str, body: JobUpdate, background: BackgroundTasks, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.external_id == external_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if body.title is not None:
        job.title = body.title
    if body.client_id is not None:
        job.client_id = body.client_id
    if body.department is not None:
        job.department = body.department
    if body.description is not None:
        job.description = body.description
    if body.skills is not None:
        job.skills = body.skills
    if body.salary_range is not None:
        job.salary_range = body.salary_range or ""
    if body.work_location is not None:
        job.work_location = (body.work_location or "").strip().lower()
    if body.job_type is not None:
        job.job_type = (body.job_type or "").strip().lower()
    if body.recruitment_urgency is not None:
        job.recruitment_urgency = (body.recruitment_urgency or "").strip().lower()
    if body.preferred_onboarding_date is not None:
        job.preferred_onboarding_date = body.preferred_onboarding_date
    if body.min_experience is not None:
        job.min_experience = body.min_experience
    if body.education_required is not None:
        job.education_required = body.education_required or "any"
    if body.status is not None:
        s = _norm_job_status(body.status or "")
        if s not in _JOB_STATUSES:
            raise HTTPException(status_code=422, detail="status must be one of: active, on_hold, completed, cancelled")
        job.status = s

    db.commit()
    db.refresh(job)
    try:
        from api.services.sbert_cache import refresh_sbert_for_job_id

        background.add_task(refresh_sbert_for_job_id, engine, job.id, 200)
    except Exception:
        pass
    return _job_read(job)


@router.delete("/by-external/{external_id}", status_code=204)
def delete_job_by_external_id(external_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.external_id == external_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return None


@router.get("/{external_id}/stats")
def job_applicant_stats(external_id: str, db: Session = Depends(get_db)):
    """
    Applicant tracker counts for one job (single source of truth: job_applicants table).
    """
    job = db.query(Job).filter(Job.external_id == external_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    rows = (
        db.query(JobApplicant.status, func.count(JobApplicant.id))
        .filter(JobApplicant.job_id == job.id)
        .group_by(JobApplicant.status)
        .all()
    )
    counts = {str(st or "new").strip().lower(): int(n or 0) for st, n in rows}
    return {
        "job_external_id": external_id,
        "total": int(sum(counts.values())),
        "new": int(counts.get("new", 0)),
        "screened": int(counts.get("screened", 0)),
        "shortlisted": int(counts.get("shortlisted", 0)),
        "interviewed": int(counts.get("interviewed", 0)),
        "hired": int(counts.get("hired", 0)),
    }


@router.patch("/{external_id}/applicants/{candidate_external_id}/status")
def update_applicant_status(external_id: str, candidate_external_id: str, body: dict, db: Session = Depends(get_db)):
    """
    Update a candidate's pipeline status for one job.
    Single source of truth: job_applicants row.
    """
    job = db.query(Job).filter(Job.external_id == external_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    cand = db.query(Candidate).filter(Candidate.external_id == candidate_external_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    st = str(body.get("status") or "").strip().lower()
    if st not in _APPLICANT_STATUSES:
        raise HTTPException(status_code=422, detail="status must be one of: new, screened, shortlisted, interviewed, hired")
    now = datetime.utcnow()
    app = (
        db.query(JobApplicant)
        .filter(JobApplicant.job_id == job.id, JobApplicant.candidate_id == cand.id)
        .first()
    )
    if not app:
        app = JobApplicant(job_id=job.id, candidate_id=cand.id, status=st, updated_at=now)
        db.add(app)
    else:
        app.status = st
        app.updated_at = now
    db.commit()
    return {"job_external_id": external_id, "candidate_external_id": candidate_external_id, "status": st}


@router.get("/{external_job_id}/attachments", response_model=list[JobAttachmentRead])
def list_job_attachments(
    external_job_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(require_user_if_auth_enabled),
):
    job = db.query(Job).filter(Job.external_id == external_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    rows = (
        db.query(JobAttachment)
        .filter(JobAttachment.job_id == job.id)
        .order_by(JobAttachment.created_at.desc())
        .all()
    )
    return [
        JobAttachmentRead(
            id=r.id,
            job_external_id=external_job_id,
            filename=r.filename or "",
            content_type=r.content_type or "application/octet-stream",
            size_bytes=int(r.size_bytes or 0),
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/{external_job_id}/attachments", response_model=JobAttachmentRead, status_code=201)
def upload_job_attachment(
    external_job_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: object = Depends(require_user_if_auth_enabled),
):
    job = db.query(Job).filter(Job.external_id == external_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not file.filename:
        raise RezumeAPIError("MISSING_FILENAME", "Missing filename.", 400)

    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct and ct not in _ALLOWED_ATTACH_CT:
        raise RezumeAPIError("UNSUPPORTED_MEDIA_TYPE", f"Content-Type not accepted: {ct}", 415)

    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise RezumeAPIError(
            "FILE_TOO_LARGE",
            f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
            413,
        )

    safe = _safe_filename(file.filename)
    root = _storage_root()
    target_dir = root / "jobs" / external_job_id
    target_dir.mkdir(parents=True, exist_ok=True)
    disk_path = target_dir / f"{job.id.hex}_{safe}"
    try:
        disk_path.write_bytes(content)
    except Exception as e:
        raise RezumeAPIError("STORE_FAILED", "Could not store attachment.", 500) from e

    row = JobAttachment(
        job_id=job.id,
        filename=safe,
        content_type=ct or (mimetypes.guess_type(safe)[0] or "application/octet-stream"),
        size_bytes=len(content),
        storage_path=str(disk_path),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return JobAttachmentRead(
        id=row.id,
        job_external_id=external_job_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )


@router.get("/{external_job_id}/attachments/{attachment_id}")
def download_job_attachment(
    external_job_id: str,
    attachment_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_user_if_auth_enabled),
):
    job = db.query(Job).filter(Job.external_id == external_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    row = (
        db.query(JobAttachment)
        .filter(JobAttachment.id == attachment_id, JobAttachment.job_id == job.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    p = Path((row.storage_path or "").strip())
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = (row.content_type or "").strip() or mimetypes.guess_type(row.filename or p.name)[0] or "application/octet-stream"
    return FileResponse(
        path=str(p),
        filename=row.filename or p.name,
        media_type=media_type,
        content_disposition_type="attachment",
    )


@router.delete("/{external_job_id}/attachments/{attachment_id}", status_code=204)
def delete_job_attachment(
    external_job_id: str,
    attachment_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_user_if_auth_enabled),
):
    job = db.query(Job).filter(Job.external_id == external_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    row = (
        db.query(JobAttachment)
        .filter(JobAttachment.id == attachment_id, JobAttachment.job_id == job.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    # Best-effort remove disk file.
    try:
        p = Path((row.storage_path or "").strip())
        if p.exists() and p.is_file():
            p.unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(row)
    db.commit()
    return None
