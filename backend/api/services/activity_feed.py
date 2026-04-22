"""
Aggregate recent system activity for dashboard / inbox notifications.

Sources: activity log, new jobs, ranking runs, human feedback (shortlist, etc.). New candidates
appear via ActivityEvent only (name + added to pool), not raw ingestion rows.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from api.models import ActivityEvent, Candidate, HumanRankingFeedback, Job, JobCandidateRanking
from api.services.candidate_display import display_full_name_from_db

_log = logging.getLogger("rezume.api")


def _iso(dt: datetime | None) -> str:
    """UTC instant with Z suffix for consistent browser parsing."""
    if dt is None:
        t = datetime.utcnow()
        return t.isoformat() + "Z"
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc.isoformat() + "Z"


def _feedback_message(action: str, cand_name: str, job_label: str) -> str:
    a = (action or "").strip().lower()
    name = (cand_name or "").strip() or "A candidate"
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


def _feedback_kind(action: str) -> str:
    """Map HumanRankingFeedback.action to a notification kind."""
    a = (action or "").strip().lower()
    if a in ("shortlisted", "shortlist"):
        return "shortlist"
    if a in ("selected", "select"):
        return "select"
    if a in ("rejected", "reject", "not_a_fit"):
        return "reject"
    return "feedback"


def build_activity_notifications(
    db: Session, limit: int = 80, recruiter_workspace_id: Optional[UUID] = None
) -> list[dict[str, Any]]:
    """
    Return newest-first activity items. Each has id, kind, message, at, optional href.

    When ``recruiter_workspace_id`` is set (authenticated recruiter), only include items tied to jobs
    in that workspace. ActivityEvent rows are omitted (they are not attributed per-workspace).
    """
    items: list[dict[str, Any]] = []
    recent_cutoff = datetime.utcnow() - timedelta(days=14)

    # 0) Explicit activity log — strictly scoped to the recruiter's workspace.
    # NULL-workspace events are legacy/global and must NEVER bleed to authenticated recruiters
    # to prevent cross-tenant notification leakage.
    try:
        evq = db.query(ActivityEvent)
        if recruiter_workspace_id is not None:
            # Strict workspace isolation: only show this recruiter's own events.
            # Legacy NULL-workspace events are intentionally excluded to prevent leakage.
            evq = evq.filter(ActivityEvent.workspace_id == recruiter_workspace_id)
        else:
            # Unauthenticated / global view: only show NULL-workspace (legacy) events.
            # Exclude per-user rows (candidate portal notifications) so they never appear here.
            evq = evq.filter(ActivityEvent.workspace_id.is_(None), ActivityEvent.user_id.is_(None))
        for ev in evq.order_by(desc(ActivityEvent.created_at)).limit(40).all():
            msg = (ev.message or "").strip() or "Update"
            low = msg.lower()
            kind = (ev.kind or "info").strip() or "info"
            # Drop legacy / noisy ingestion lines (only surface "… added to the pool" via candidate_added / success)
            if kind == "upload":
                continue
            if "upload queued:" in low or "processing upload:" in low or low.startswith("resume upload ("):
                continue
            items.append(
                {
                    "id": f"event-{ev.id}",
                    "kind": kind,
                    "message": msg,
                    "at": _iso(ev.created_at),
                    "href": (ev.href or "").strip() or None,
                }
            )
    except Exception as e:
        _log.debug("activity_feed events skipped: %s", e)

    # Ingestion rows are not listed here (no queued/processing/upload noise). Successful adds
    # appear as ActivityEvent from ingestions/candidates routers: "{name} added to the pool".

    try:
        jq = db.query(Job).filter(Job.created_at >= recent_cutoff)
        if recruiter_workspace_id is not None:
            jq = jq.filter(Job.workspace_id == recruiter_workspace_id)
        for j in jq.order_by(desc(Job.created_at)).limit(12).all():
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
            if recruiter_workspace_id is not None and getattr(j, "workspace_id", None) != recruiter_workspace_id:
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
            ext = (j.external_id or "").strip()
            items.append(
                {
                    "id": f"rank-{job_id}-{lr_key}",
                    "kind": "ranking",
                    "message": msg,
                    "at": _iso(last_run),
                    # Jobs list + modal for this job (not /jobs/:id legacy page)
                    "href": f"/jobs?job={quote(ext, safe='')}" if ext else None,
                }
            )
    except Exception as e:
        _log.debug("activity_feed rankings skipped: %s", e)

    try:
        fbq = db.query(HumanRankingFeedback).filter(HumanRankingFeedback.created_at >= recent_cutoff)
        if recruiter_workspace_id is not None:
            fbq = fbq.join(Job, Job.id == HumanRankingFeedback.job_id).filter(Job.workspace_id == recruiter_workspace_id)
        for fb in fbq.order_by(desc(HumanRankingFeedback.created_at)).limit(25).all():
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
                    "kind": _feedback_kind(fb.action),
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


def build_candidate_user_notifications(db: Session, user_id: UUID, limit: int = 60) -> list[dict[str, Any]]:
    """Activity rows for a candidate account (ActivityEvent.user_id = linked user)."""
    items: list[dict[str, Any]] = []
    try:
        for ev in (
            db.query(ActivityEvent)
            .filter(ActivityEvent.user_id == user_id)
            .order_by(desc(ActivityEvent.created_at))
            .limit(limit)
            .all()
        ):
            hid = (ev.href or "").strip() or None
            items.append(
                {
                    "id": f"event-{ev.id}",
                    "kind": (ev.kind or "info").strip() or "info",
                    "message": (ev.message or "").strip() or "Update",
                    "at": _iso(ev.created_at),
                    "href": hid,
                }
            )
    except Exception as e:
        _log.debug("build_candidate_user_notifications skipped: %s", e)
    return items
