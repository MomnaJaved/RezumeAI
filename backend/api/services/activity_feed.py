"""
Aggregate recent system activity for dashboard / inbox notifications.

Sources: ingestions, new jobs, new candidates, ranking runs, human feedback (shortlist, etc.).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from api.models import ActivityEvent, Candidate, HumanRankingFeedback, Job, JobCandidateRanking, ResumeIngestion
from api.services.candidate_display import display_full_name_from_db
from src.parsing.name_extractor import UNKNOWN_CANDIDATE

_log = logging.getLogger("rezume.api")


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return datetime.utcnow().isoformat()
    return dt.isoformat()


def _feedback_message(action: str, cand_name: str, job_label: str) -> str:
    a = (action or "").strip().lower()
    name = cand_name or UNKNOWN_CANDIDATE
    job = job_label or "job"
    if a in ("shortlisted", "shortlist"):
        return f"{name} shortlisted for {job}"
    if a in ("selected", "select"):
        return f"{name} marked as selected for {job}"
    if a in ("rejected", "reject"):
        return f"{name} marked not a fit for {job}"
    if a == "not_a_fit":
        return f"{name} marked not a fit for {job}"
    return f"{name}: {action or 'update'} — {job}"


def build_activity_notifications(db: Session, limit: int = 80) -> list[dict[str, Any]]:
    """
    Return newest-first activity items. Each has id, kind, message, at, optional href.
    """
    items: list[dict[str, Any]] = []
    recent_cutoff = datetime.utcnow() - timedelta(days=14)

    # 0) Explicit activity log (append-only; used for deletes and user-facing events).
    try:
        for ev in (
            db.query(ActivityEvent)
            .order_by(desc(ActivityEvent.created_at))
            .limit(40)
            .all()
        ):
            items.append(
                {
                    "id": f"event-{ev.id}",
                    "kind": (ev.kind or "info").strip() or "info",
                    "message": (ev.message or "").strip() or "Update",
                    "at": _iso(ev.created_at),
                    "href": (ev.href or "").strip() or None,
                }
            )
    except Exception as e:
        _log.debug("activity_feed events skipped: %s", e)

    try:
        for r in db.query(ResumeIngestion).order_by(desc(ResumeIngestion.updated_at)).limit(20).all():
            ts = r.updated_at or r.created_at
            fn = (r.filename or "resume").strip() or "resume"
            if r.status == "done":
                msg = f"Resume uploaded: {fn} — added to the pool"
                items.append(
                    {
                        "id": f"ingestion-{r.id}",
                        "kind": "upload",
                        "message": msg,
                        "at": _iso(ts),
                        "href": "/candidates",
                    }
                )
            elif r.status == "failed":
                msg = f"Resume upload failed: {fn}. Please try again."
                items.append(
                    {
                        "id": f"ingestion-fail-{r.id}",
                        "kind": "upload",
                        "message": msg,
                        "at": _iso(ts),
                        "href": "/ingest",
                    }
                )
            elif r.status == "queued":
                items.append(
                    {
                        "id": f"ingestion-queued-{r.id}",
                        "kind": "upload",
                        "message": f"Upload queued: {fn}",
                        "at": _iso(ts),
                        "href": "/ingest",
                    }
                )
            elif r.status == "processing":
                items.append(
                    {
                        "id": f"ingestion-processing-{r.id}",
                        "kind": "upload",
                        "message": f"Processing upload: {fn}",
                        "at": _iso(ts),
                        "href": "/ingest",
                    }
                )
            else:
                items.append(
                    {
                        "id": f"ingestion-{r.status}-{r.id}",
                        "kind": "upload",
                        "message": f"Resume upload ({r.status}): {fn}",
                        "at": _iso(ts),
                        "href": "/ingest",
                    }
                )
    except Exception as e:
        _log.debug("activity_feed ingestions skipped: %s", e)

    try:
        for j in (
            db.query(Job)
            .filter(Job.created_at >= recent_cutoff)
            .order_by(desc(Job.created_at))
            .limit(12)
            .all()
        ):
            label = (j.title or "").strip() or j.external_id
            items.append(
                {
                    "id": f"job-{j.id}",
                    "kind": "job",
                    "message": f"New job: {label}",
                    "at": _iso(j.created_at),
                    "href": f"/jobs/{j.external_id}",
                }
            )
    except Exception as e:
        _log.debug("activity_feed jobs skipped: %s", e)

    # Candidates: use explicit ActivityEvent log instead of inferred names
    # (avoids showing mis-parsed names from resume headers).

    try:
        rank_rows = (
            db.query(
                JobCandidateRanking.job_id,
                func.max(JobCandidateRanking.run_at).label("last_run"),
            )
            .group_by(JobCandidateRanking.job_id)
            .all()
        )
        rank_rows = sorted(
            rank_rows,
            key=lambda x: x[1] or datetime.min,
            reverse=True,
        )[:12]
        for job_id, last_run in rank_rows:
            if last_run is None:
                continue
            j = db.query(Job).filter(Job.id == job_id).first()
            if not j:
                continue
            label = (j.title or "").strip() or j.external_id
            n = (
                db.query(JobCandidateRanking)
                .filter(JobCandidateRanking.job_id == job_id, JobCandidateRanking.run_at == last_run)
                .count()
            )
            top = (
                db.query(JobCandidateRanking)
                .filter(JobCandidateRanking.job_id == job_id, JobCandidateRanking.run_at == last_run)
                .order_by(JobCandidateRanking.rank_position)
                .first()
            )
            top_name = ""
            if top and (top.candidate_name or "").strip():
                top_name = (top.candidate_name or "").strip()
            msg = f"Ranking updated for {label} ({n} candidates scored)"
            if top_name:
                msg += f" — top match: {top_name}"
            lr_key = last_run.isoformat() if hasattr(last_run, "isoformat") else str(last_run)
            items.append(
                {
                    "id": f"rank-{job_id}-{lr_key}",
                    "kind": "ranking",
                    "message": msg,
                    "at": _iso(last_run),
                    "href": f"/jobs/{j.external_id}",
                }
            )
    except Exception as e:
        _log.debug("activity_feed rankings skipped: %s", e)

    try:
        for fb in (
            db.query(HumanRankingFeedback)
            .filter(HumanRankingFeedback.created_at >= recent_cutoff)
            .order_by(desc(HumanRankingFeedback.created_at))
            .limit(25)
            .all()
        ):
            job = db.query(Job).filter(Job.id == fb.job_id).first()
            cand = db.query(Candidate).filter(Candidate.id == fb.candidate_id).first()
            job_label = ""
            if job:
                job_label = (job.title or "").strip() or job.external_id
            cand_name = display_full_name_from_db(cand.full_name) if cand else ""
            msg = _feedback_message(fb.action, cand_name, job_label)
            jid = job.external_id if job else ""
            items.append(
                {
                    "id": f"feedback-{fb.id}",
                    "kind": "feedback",
                    "message": msg,
                    "at": _iso(fb.created_at),
                    "href": f"/jobs/{jid}" if jid else "/candidates",
                }
            )
    except Exception as e:
        _log.debug("activity_feed feedback skipped: %s", e)

    def _parse_at(s: str) -> datetime:
        try:
            t = str(s).replace("Z", "+00:00")
            return datetime.fromisoformat(t)
        except ValueError:
            return datetime.min

    items.sort(key=lambda x: _parse_at(str(x["at"])), reverse=True)
    return items[:limit]
