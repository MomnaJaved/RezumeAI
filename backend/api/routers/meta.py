"""Model versions and light operational stats."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.models import Candidate, Job, ResumeIngestion
from api.paths import repo_root

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/models")
def model_versions():
    s = get_settings()
    root = repo_root()
    role_dir = root / "artifacts" / "role_classifier" / "config.json"
    match_dir = root / "artifacts" / "match_ranker" / "config.json"
    return {
        "versions": {
            "tfidf": s.model_version_tfidf,
            "sbert": s.model_version_sbert,
            "cross_encoder": s.model_version_crossencoder,
            "role_classifier": s.model_version_role,
        },
        "artifacts_present": {
            "role_classifier": role_dir.is_file(),
            "match_ranker": match_dir.is_file(),
        },
        "active_inference": {
            "role": s.model_version_role if role_dir.is_file() else None,
            "match": s.model_version_crossencoder if match_dir.is_file() else None,
        },
    }


@router.get("/stats")
def quick_stats(db: Session = Depends(get_db)):
    return {
        "candidates_total": db.query(Candidate).count(),
        "jobs_total": db.query(Job).count(),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """
    Dashboard data for the frontend: overview counts + lightweight notifications.
    Safe for SQLite/Postgres; if resume_ingestions table isn't present in older DBs, returns zeros.
    """
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)

    candidates_total = db.query(Candidate).count()
    jobs_total = db.query(Job).count()
    new_candidates_24h = db.query(Candidate).filter(Candidate.created_at >= since_24h).count()

    ingestions_queued = 0
    ingestions_processing = 0
    ingestions_done_24h = 0
    ingestion_notes: list[dict] = []
    try:
        ingestions_queued = db.query(ResumeIngestion).filter(ResumeIngestion.status == "queued").count()
        ingestions_processing = db.query(ResumeIngestion).filter(ResumeIngestion.status == "processing").count()
        ingestions_done_24h = (
            db.query(ResumeIngestion)
            .filter(ResumeIngestion.status == "done")
            .filter(ResumeIngestion.updated_at >= since_24h)
            .count()
        )
        latest_ing = db.query(ResumeIngestion).order_by(desc(ResumeIngestion.updated_at)).limit(6).all()
        ingestion_notes = [
            {
                "kind": "ingestion",
                "message": f'{r.filename or "resume"} → {r.status}',
                "at": (r.updated_at or r.created_at).isoformat(),
            }
            for r in latest_ing
        ]
    except Exception:
        pass

    latest_jobs = db.query(Job).order_by(desc(Job.created_at)).limit(3).all()
    job_notes = [
        {
            "kind": "job",
            "message": f'Job created: {j.title or j.external_id}',
            "at": j.created_at.isoformat(),
        }
        for j in latest_jobs
    ]

    notifications = (ingestion_notes + job_notes)[:8]
    return {
        "overview": {
            "candidates_total": candidates_total,
            "jobs_total": jobs_total,
            "new_candidates_24h": new_candidates_24h,
            "ingestions_queued": ingestions_queued,
            "ingestions_processing": ingestions_processing,
            "ingestions_done_24h": ingestions_done_24h,
        },
        "notifications": notifications,
    }
