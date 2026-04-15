"""Model versions and light operational stats."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.models import Candidate, Job, ResumeIngestion
from api.paths import repo_root
from api.services.activity_feed import build_activity_notifications
from api.services.dashboard_widgets import build_dashboard_preview_job_breadth_scores, build_dashboard_widgets

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
        "jobs_total": db.query(Job).filter(Job.status == "active").count(),
    }


@router.get("/dashboard/widgets")
def dashboard_widgets(db: Session = Depends(get_db)):
    """
    Applicant pipeline, jobs breakdown, and candidate preview for the home dashboard.
    Candidate summary scores are cohort profile percentiles (same field as the candidates list).
    """
    return build_dashboard_widgets(db)


@router.get("/dashboard/widgets/preview-scores")
def dashboard_widgets_preview_scores(db: Session = Depends(get_db)):
    """Same candidate preview scores as GET /meta/dashboard/widgets (legacy alias)."""
    return build_dashboard_preview_job_breadth_scores(db)


@router.get("/activity")
def activity_feed(db: Session = Depends(get_db)):
    """Lightweight poll endpoint for live notifications (same items as dashboard feed)."""
    return {"notifications": build_activity_notifications(db, limit=60)}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """
    Dashboard data for the frontend: overview counts + lightweight notifications.
    Safe for SQLite/Postgres; if resume_ingestions table isn't present in older DBs, returns zeros.
    """
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)

    candidates_total = db.query(Candidate).count()
    jobs_total = db.query(Job).filter(Job.status == "active").count()
    new_candidates_24h = db.query(Candidate).filter(Candidate.created_at >= since_24h).count()

    ingestions_queued = 0
    ingestions_processing = 0
    ingestions_done_24h = 0
    try:
        ingestions_queued = db.query(ResumeIngestion).filter(ResumeIngestion.status == "queued").count()
        ingestions_processing = db.query(ResumeIngestion).filter(ResumeIngestion.status == "processing").count()
        ingestions_done_24h = (
            db.query(ResumeIngestion)
            .filter(ResumeIngestion.status == "done")
            .filter(ResumeIngestion.updated_at >= since_24h)
            .count()
        )
    except Exception:
        pass

    notifications = build_activity_notifications(db, limit=60)
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
