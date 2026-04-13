from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Job
from api.schemas import JobCreate, JobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRead])
def list_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit)
    return list(q.all())


@router.get("/by-external/{external_id}", response_model=JobRead)
def get_job_by_external_id(external_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.external_id == external_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_uuid}", response_model=JobRead)
def get_job(job_uuid: UUID, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("", response_model=JobRead, status_code=201)
def create_job(body: JobCreate, db: Session = Depends(get_db)):
    existing = db.query(Job).filter(Job.external_id == body.external_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Job with this external_id already exists")
    job = Job(
        external_id=body.external_id,
        title=body.title,
        department=body.department,
        description=body.description,
        skills=body.skills,
        min_experience=body.min_experience,
        education_required=body.education_required or "any",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
