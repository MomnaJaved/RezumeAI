"""
Aggregate recent system activity for dashboard / inbox notifications.

Sources: ingestions, new jobs, new candidates, ranking runs, human feedback (shortlist, etc.).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from api.models import Candidate, HumanRankingFeedback, Job, JobCandidateRanking, ResumeIngestion

_log = logging.getLogger("rezume.api")


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return datetime.utcnow().isoformat()
    return dt.isoformat()


def _feedback_message(action: str, cand_name: str, job_label: str) -> str:
    a = (action or "").strip().lower()
    name = cand_name or "Candidate"
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

    try:
        for r in db.query(ResumeIngestion).order_by(desc(ResumeIngestion.updated_at)).limit(20).all():
            ts = r.updated_at or r.created_at
            fn = (r.filename or "resume").strip() or "resume"
            if r.status == "done":
                msg = f"Resume ingested: {fn}"
                if (r.candidate_external_id or "").strip():
                    msg += f" → candidate {r.candidate_external_id.strip()}"
                else:
                    msg += " — added to pool"
                items.append(
                    {
                        "id": f"ingestion-{r.id}",
                        "kind": "ingestion",
                        "message": msg,
                        "at": _iso(ts),
                        "href": "/candidates",
                    }
                )
            elif r.status == "failed":
                err = (r.error or "").strip()[:120]
                msg = f"Ingestion failed: {fn}"
                if err:
                    msg += f" ({err})"
                items.append(
                    {
                        "id": f"ingestion-fail-{r.id}",
                        "kind": "ingestion",
                        "message": msg,
                        "at": _iso(ts),
                        "href": "/ingest",
                    }
                )
            else:
                items.append(
                    {
                        "id": f"ingestion-{r.status}-{r.id}",
                        "kind": "ingestion",
                        "message": f"{fn} — {r.status}",
                        "at": _iso(ts),
                        "href": "/ingest",
                    }
                )
    except Exception as e:
        _log.debug("activity_feed ingestions skipped: %s", e)

    try:
        for j in db.query(Job).order_by(desc(Job.created_at)).limit(8).all():
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

    try:
        for c in db.query(Candidate).order_by(desc(Candidate.created_at)).limit(15).all():
            name = (c.full_name or "").strip() or c.external_id
            items.append(
                {
                    "id": f"candidate-{c.id}",
                    "kind": "candidate",
                    "message": f"New candidate in pool: {name}",
                    "at": _iso(c.created_at),
                    "href": "/candidates",
                }
            )
    except Exception as e:
        _log.debug("activity_feed candidates skipped: %s", e)

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
        for fb in db.query(HumanRankingFeedback).order_by(desc(HumanRankingFeedback.created_at)).limit(20).all():
            job = db.query(Job).filter(Job.id == fb.job_id).first()
            cand = db.query(Candidate).filter(Candidate.id == fb.candidate_id).first()
            job_label = ""
            if job:
                job_label = (job.title or "").strip() or job.external_id
            cand_name = ""
            if cand:
                cand_name = (cand.full_name or "").strip() or cand.external_id
            msg = _human_action_message(fb.action, cand_name, job_label)
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
