"""Model versions and light operational stats."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.dependencies import get_current_user_optional, recruiter_meta_scope, require_user_if_auth_enabled
from api.models import ActivityEvent, Candidate, Job, JobApplicant, ResumeIngestion, User
from api.paths import repo_root
from api.services.activity_feed import build_activity_notifications, build_candidate_user_notifications
from api.services.workspace_scope import candidate_visibility_predicate, ensure_workspace_for_recruiter
from api.services.activity_log import log_activity
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
def quick_stats(
    db: Session = Depends(get_db),
    recruiter_workspace_id: Optional[UUID] = Depends(recruiter_meta_scope),
):
    if recruiter_workspace_id is not None:
        from api.services.workspace_scope import candidate_visibility_predicate
        from sqlalchemy import func as _func
        candidates_total = db.query(_func.count(Candidate.id)).filter(candidate_visibility_predicate(recruiter_workspace_id)).scalar() or 0
        jobs_total = db.query(Job).filter(Job.status == "active", Job.workspace_id == recruiter_workspace_id).count()
    else:
        candidates_total = db.query(Candidate).count()
        jobs_total = db.query(Job).filter(Job.status == "active").count()
    return {
        "candidates_total": candidates_total,
        "jobs_total": jobs_total,
    }


@router.get("/dashboard/widgets")
def dashboard_widgets(
    db: Session = Depends(get_db),
    recruiter_workspace_id: Optional[UUID] = Depends(recruiter_meta_scope),
):
    """
    Applicant pipeline, jobs breakdown, and candidate preview for the home dashboard.
    Candidate summary scores are cohort profile percentiles (same field as the candidates list).
    """
    return build_dashboard_widgets(db, recruiter_workspace_id=recruiter_workspace_id)


@router.get("/dashboard/widgets/preview-scores")
def dashboard_widgets_preview_scores(
    db: Session = Depends(get_db),
    recruiter_workspace_id: Optional[UUID] = Depends(recruiter_meta_scope),
):
    """Same candidate preview scores as GET /meta/dashboard/widgets (legacy alias)."""
    return build_dashboard_preview_job_breadth_scores(db, recruiter_workspace_id=recruiter_workspace_id)


@router.get("/activity")
def activity_feed(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Lightweight poll endpoint for live notifications (same items as dashboard feed for recruiters).

    Scoping rules (mirrors :func:`recruiter_meta_scope`):
    - Authenticated recruiter → only activity for jobs in their workspace, even
      when ``REQUIRE_AUTH`` is off (prevents cross-tenant leakage on a shared DB).
    - Candidate accounts → personal notifications (pipeline, scores) for the linked user.
    - No user with ``REQUIRE_AUTH=true`` → 401.
    - No user with ``REQUIRE_AUTH=false`` → global feed (legacy clients / tests).
    """
    settings = get_settings()
    if user is None:
        if settings.require_auth:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        return {"notifications": build_activity_notifications(db, limit=60, recruiter_workspace_id=None)}
    role = (getattr(user, "account_role", None) or "recruiter").strip().lower()
    if role == "candidate":
        return {"notifications": build_candidate_user_notifications(db, user.id, limit=60)}
    wid = ensure_workspace_for_recruiter(db, user)
    return {
        "notifications": build_activity_notifications(db, limit=60, recruiter_workspace_id=wid),
    }


@router.delete("/activity", status_code=204)
def clear_activity(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Delete activity events visible to the current recruiter.
    Only deletes workspace-owned events — never touches NULL-workspace (global/legacy) rows
    so one recruiter clearing their feed cannot wipe another recruiter's notifications.
    """
    ws_id = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        ws_id = ensure_workspace_for_recruiter(db, user)
    if ws_id is not None:
        # Strict: only delete this recruiter's own workspace events.
        db.query(ActivityEvent).filter(ActivityEvent.workspace_id == ws_id).delete(synchronize_session=False)
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() == "candidate":
        db.query(ActivityEvent).filter(ActivityEvent.user_id == user.id).delete(synchronize_session=False)
    # No-op for unauthenticated callers.
    db.commit()
    return


class LogActivityBody(BaseModel):
    kind: str = "info"
    message: str = ""
    href: str = ""


@router.post("/log")
def log_activity_endpoint(
    body: LogActivityBody,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """Frontend-initiated activity log entry (e.g. low match warnings after ranking)."""
    ws_id = None
    uid = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        ws_id = ensure_workspace_for_recruiter(db, user)
        uid = user.id
    log_activity(db, kind=body.kind[:64], message=body.message[:512], href=body.href[:256], workspace_id=ws_id, user_id=uid)
    return {"ok": True}


@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    recruiter_workspace_id: Optional[UUID] = Depends(recruiter_meta_scope),
):
    """
    Dashboard data for the frontend: overview counts + lightweight notifications.
    Safe for SQLite/Postgres; if resume_ingestions table isn't present in older DBs, returns zeros.
    """
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)

    if recruiter_workspace_id is not None:
        jobs_total = db.query(Job).filter(Job.status == "active", Job.workspace_id == recruiter_workspace_id).count()
        # Count every candidate visible to this workspace — owned directly
        # (uploaded by this recruiter) OR linked via any job in the workspace.
        # Counting only via JobApplicant excluded freshly uploaded candidates
        # that hadn't been attached to a job yet, so a new account that had
        # uploaded resumes would still see 0 candidates on the dashboard.
        vis = candidate_visibility_predicate(recruiter_workspace_id)
        candidates_total = db.query(func.count(Candidate.id)).filter(vis).scalar() or 0
        new_candidates_24h = (
            db.query(func.count(Candidate.id))
            .filter(vis, Candidate.created_at >= since_24h)
            .scalar()
            or 0
        )
    else:
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

    notifications = build_activity_notifications(db, limit=60, recruiter_workspace_id=recruiter_workspace_id)
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
