"""In-app notifications for linked candidate accounts (ActivityEvent with user_id, workspace NULL)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from api.models import Candidate, Job, JobApplicant
from api.services.activity_log import log_activity


def _job_label(job: Job) -> str:
    return (job.title or "").strip() or (job.external_id or "").strip() or "this role"


def _applications_href() -> str:
    return "/candidate/applications"


def notify_candidate_pipeline_status(db: Session, job: Job, cand: Candidate, status: str) -> None:
    """Notify the candidate user when pipeline status changes (linked account only)."""
    uid = getattr(cand, "user_id", None)
    if uid is None:
        return
    label = _job_label(job)
    href = _applications_href()
    st = (status or "").strip().lower()
    if st in ("new",):
        return
    if st == "shortlisted":
        kind, msg = "shortlist", f"You were shortlisted for {label}."
    elif st == "selected":
        kind, msg = "select", f"You were selected for {label}."
    elif st in ("interviewing", "interviewed"):
        kind, msg = "interview", f"Your application for {label} moved to interviewing."
    elif st == "hired":
        kind, msg = "hired", f"You were marked as hired for {label}."
    elif st == "rejected":
        kind, msg = "reject", f"An update on {label}: this role is not moving forward with your application right now."
    elif st == "screened":
        kind, msg = "screened", f"Your application for {label} was reviewed."
    else:
        kind, msg = "pipeline", f'Your status for {label} was updated to "{st}".'

    log_activity(db, kind=kind[:64], message=msg[:512], href=href[:256], workspace_id=None, user_id=uid)


def notify_applicants_ranking_updated(
    db: Session,
    job: Job,
    ranked: list[tuple[Candidate, int, float]],
    applicant_ids: set[UUID] | None = None,
) -> None:
    """
    Notify portal candidates who applied to this job when a saved ranking includes them.

    ``ranked`` is (candidate, rank_position, cross_encoder_score) with score in 0–1.
    """
    if applicant_ids is None:
        applicant_ids = {
            cid for (cid,) in db.query(JobApplicant.candidate_id).filter(JobApplicant.job_id == job.id).all()
        }
    if not applicant_ids:
        return
    label = _job_label(job)
    href = _applications_href()
    for cand, pos, score in ranked:
        uid = getattr(cand, "user_id", None)
        if uid is None or cand.id not in applicant_ids:
            continue
        pct = round(float(score) * 100.0, 1)
        msg = f"Your match score for {label} was updated — rank #{pos}, score {pct}/100."
        log_activity(db, kind="ranking", message=msg[:512], href=href[:256], workspace_id=None, user_id=uid)
