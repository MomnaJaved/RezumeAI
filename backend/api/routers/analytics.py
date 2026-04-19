from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, or_
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import recruiter_meta_scope
from api.models import Candidate, Client, Job, JobApplicant, JobCandidateRanking
from api.services.applicant_status_effective import (
    applicant_pairs_for_job_ids,
    applicant_tracker_counts,
    global_applicant_status_created_pairs,
    recruiter_applicant_status_created_pairs,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
_log = logging.getLogger("rezume.api")


@router.get("/applicant-stats")
def applicant_stats(
    db: Session = Depends(get_db),
    recruiter_workspace_id: Optional[UUID] = Depends(recruiter_meta_scope),
):
    """
    Applicant tracker counts. With REQUIRE_AUTH on, scoped to applications for jobs in the recruiter workspace.
    With auth off, global counts (includes orphan candidates without a job application row).
    """
    if recruiter_workspace_id is not None:
        pairs = recruiter_applicant_status_created_pairs(db, recruiter_workspace_id)
    else:
        pairs = global_applicant_status_created_pairs(db)
    agg = applicant_tracker_counts(pairs)
    iv = int(agg["interviewing"])
    return {
        "total": int(agg["total"]),
        "new": int(agg["new"]),
        "screened": int(agg["screened"]),
        "shortlisted": int(agg["shortlisted"]),
        "interviewing": iv,
        "interviewed": iv,
        "hired": int(agg["hired"]),
        "rejected": int(agg["rejected"]),
    }


@router.get("/reports")
def reports_overview(
    client_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    job_external_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    recruiter_workspace_id: Optional[UUID] = Depends(recruiter_meta_scope),
):
    """
    Comprehensive hiring performance report.
    Returns KPIs, pipeline funnel, per-job performance, and AI vs manual screening metrics.
    All filters are optional; omitting them returns global stats.
    """
    # ── Date parsing ──────────────────────────────────────────────────────────
    dt_from: Optional[datetime] = None
    dt_to: Optional[datetime] = None
    for raw, slot in [(date_from, "from"), (date_to, "to")]:
        if not raw:
            continue
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                parsed = datetime.strptime(raw[:26], fmt)
                if slot == "from":
                    dt_from = parsed
                else:
                    dt_to = parsed
                break
            except ValueError:
                continue

    is_filtered = bool(client_id or dt_from or dt_to or job_external_id)

    # ── Filtered job set ──────────────────────────────────────────────────────
    job_q = db.query(Job)
    if recruiter_workspace_id is not None:
        job_q = job_q.filter(Job.workspace_id == recruiter_workspace_id)
    if client_id:
        try:
            job_q = job_q.filter(Job.client_id == UUID(client_id))
        except Exception:
            pass
    if dt_from:
        job_q = job_q.filter(Job.created_at >= dt_from)
    if dt_to:
        job_q = job_q.filter(Job.created_at <= dt_to)
    if job_external_id:
        job_q = job_q.filter(Job.external_id == job_external_id)

    if is_filtered:
        filtered_jobs = job_q.all()
        job_ids = [j.id for j in filtered_jobs]
        total_jobs = len(job_ids)
        perf_jobs = filtered_jobs[:15]
        # Early exit if no matching jobs
        if not job_ids:
            cq = db.query(Client)
            jq = db.query(Job)
            if recruiter_workspace_id is not None:
                sub_ids = (
                    db.query(Job.client_id)
                    .filter(Job.workspace_id == recruiter_workspace_id, Job.client_id.isnot(None))
                    .distinct()
                )
                cq = cq.filter(or_(Client.workspace_id == recruiter_workspace_id, Client.id.in_(sub_ids)))
                jq = jq.filter(Job.workspace_id == recruiter_workspace_id)
            clients_list = [{"id": str(c.id), "name": c.name} for c in cq.order_by(Client.name).all()]
            jobs_filter_list = [
                {"external_id": j.external_id, "title": (j.title or j.external_id).strip()} for j in jq.order_by(Job.title).all()
            ]
            return _empty_report(clients_list, jobs_filter_list)
    else:
        if recruiter_workspace_id is not None:
            total_jobs = int(
                db.query(func.count(Job.id))
                .filter(Job.workspace_id == recruiter_workspace_id, Job.status == "active")
                .scalar()
                or 0
            )
            job_ids = []
            perf_jobs = (
                db.query(Job)
                .filter(Job.workspace_id == recruiter_workspace_id)
                .order_by(Job.created_at.desc())
                .limit(15)
                .all()
            )
        else:
            total_jobs = int(db.query(func.count(Job.id)).filter(Job.status == "active").scalar() or 0)
            job_ids = []
            perf_jobs = db.query(Job).order_by(Job.created_at.desc()).limit(15).all()

    # ── Total candidates ──────────────────────────────────────────────────────
    if is_filtered and job_ids:
        total_candidates = int(
            db.query(func.count(distinct(JobApplicant.candidate_id)))
            .filter(JobApplicant.job_id.in_(job_ids))
            .scalar() or 0
        )
    else:
        if recruiter_workspace_id is not None:
            total_candidates = int(
                db.query(func.count(distinct(JobApplicant.candidate_id)))
                .select_from(JobApplicant)
                .join(Job, Job.id == JobApplicant.job_id)
                .filter(Job.workspace_id == recruiter_workspace_id)
                .scalar()
                or 0
            )
        else:
            total_candidates = int(db.query(func.count(Candidate.id)).scalar() or 0)

    # ── Pipeline funnel (same rules as dashboard widgets: TTL "new→screened", merged shortlisted+selected)
    if is_filtered and job_ids:
        report_pairs = applicant_pairs_for_job_ids(db, job_ids)
    elif recruiter_workspace_id is not None:
        report_pairs = recruiter_applicant_status_created_pairs(db, recruiter_workspace_id)
    else:
        report_pairs = global_applicant_status_created_pairs(db)
    agg = applicant_tracker_counts(report_pairs)
    pipeline = {
        "new": int(agg["new"]),
        "screened": int(agg["screened"]),
        "shortlisted": int(agg["shortlisted"]),
        "interviewing": int(agg["interviewing"]),
        "selected": 0,
        "hired": int(agg["hired"]),
        "rejected": int(agg["rejected"]),
        "total": int(agg["total"]),
    }
    hires = pipeline["hired"]

    # ── Average hire time (days: job created_at → applicant hired updated_at) ─
    ht_q = (
        db.query(JobApplicant.updated_at, Job.created_at)
        .join(Job, Job.id == JobApplicant.job_id)
        .filter(JobApplicant.status == "hired")
    )
    if is_filtered and job_ids:
        ht_q = ht_q.filter(JobApplicant.job_id.in_(job_ids))
    elif recruiter_workspace_id is not None:
        ht_q = ht_q.filter(Job.workspace_id == recruiter_workspace_id)
    hire_rows = ht_q.all()
    if hire_rows:
        days_list = [max(0, (ua - jc).days) for ua, jc in hire_rows if ua and jc]
        avg_hire_time_days = round(sum(days_list) / len(days_list)) if days_list else 0
    else:
        avg_hire_time_days = 0

    # ── Job performance table ─────────────────────────────────────────────────
    job_performance = []
    for j in perf_jobs:
        avg_raw = (
            db.query(func.avg(JobCandidateRanking.cross_encoder_score))
            .filter(JobCandidateRanking.job_id == j.id)
            .scalar()
        )
        hire_n = int(
            db.query(func.count(JobApplicant.id))
            .filter(JobApplicant.job_id == j.id, JobApplicant.status == "hired")
            .scalar() or 0
        )
        job_performance.append({
            "job_external_id": j.external_id,
            "job_title": (j.title or j.external_id).strip(),
            "avg_match_score": round(float(avg_raw or 0.0) * 100),
            "hires": hire_n,
        })
    job_performance.sort(key=lambda x: (x["hires"], x["avg_match_score"]), reverse=True)
    job_performance = job_performance[:10]

    # ── Derived metrics (aligned with merged funnel: shortlisted already includes selected)
    advanced = pipeline["shortlisted"] + pipeline["interviewing"] + hires
    shortlist_accuracy_pct = round(hires / advanced * 100) if advanced > 0 else 0
    # Time saved = funnel compression: fraction of candidates recruiters did NOT
    # have to manually review because AI pre-filtered them down to a shortlist.
    pipeline_total = pipeline["total"] or 1
    shortlisted_and_above = pipeline["shortlisted"] + pipeline["interviewing"] + hires
    time_saved_pct = round((1 - shortlisted_and_above / pipeline_total) * 100) if pipeline_total > 0 else 0

    # ── AI vs manual screening (contribution model) ───────────────────────────
    # Of all candidates who progressed (shortlisted+), what share had an AI
    # match score vs were picked without any AI ranking?
    # The two values always sum to 100 %, making it a true head-to-head.
    progressed = ("shortlisted", "interviewing", "selected", "hired")

    ai_cand_subq = db.query(distinct(JobCandidateRanking.candidate_id))
    if is_filtered and job_ids:
        ai_cand_subq = ai_cand_subq.filter(JobCandidateRanking.job_id.in_(job_ids))
    elif recruiter_workspace_id is not None:
        ai_cand_subq = (
            ai_cand_subq.join(Job, Job.id == JobCandidateRanking.job_id).filter(Job.workspace_id == recruiter_workspace_id)
        )

    total_prog_q = db.query(func.count(distinct(JobApplicant.candidate_id))).filter(
        JobApplicant.status.in_(progressed),
    )
    if is_filtered and job_ids:
        total_prog_q = total_prog_q.filter(JobApplicant.job_id.in_(job_ids))
    elif recruiter_workspace_id is not None:
        total_prog_q = total_prog_q.join(Job, Job.id == JobApplicant.job_id).filter(Job.workspace_id == recruiter_workspace_id)
    total_progressed = int(total_prog_q.scalar() or 0)

    ai_prog_q = db.query(func.count(distinct(JobApplicant.candidate_id))).filter(
        JobApplicant.status.in_(progressed),
        JobApplicant.candidate_id.in_(ai_cand_subq),
    )
    if is_filtered and job_ids:
        ai_prog_q = ai_prog_q.filter(JobApplicant.job_id.in_(job_ids))
    elif recruiter_workspace_id is not None:
        ai_prog_q = ai_prog_q.join(Job, Job.id == JobApplicant.job_id).filter(Job.workspace_id == recruiter_workspace_id)
    ai_progressed = int(ai_prog_q.scalar() or 0)

    ai_screening_pct = round(ai_progressed / total_progressed * 100) if total_progressed > 0 else 0
    manual_screening_pct = 100 - ai_screening_pct if total_progressed > 0 else 0

    # ── Filter dropdown data ──────────────────────────────────────────────────
    cq = db.query(Client)
    jq = db.query(Job)
    if recruiter_workspace_id is not None:
        sub_ids = (
            db.query(Job.client_id)
            .filter(Job.workspace_id == recruiter_workspace_id, Job.client_id.isnot(None))
            .distinct()
        )
        cq = cq.filter(or_(Client.workspace_id == recruiter_workspace_id, Client.id.in_(sub_ids)))
        jq = jq.filter(Job.workspace_id == recruiter_workspace_id)
    clients_list = [{"id": str(c.id), "name": c.name} for c in cq.order_by(Client.name).all()]
    jobs_filter_list = [
        {"external_id": j.external_id, "title": (j.title or j.external_id).strip()} for j in jq.order_by(Job.title).all()
    ]

    return {
        "kpi": {
            "total_jobs": total_jobs,
            "total_candidates": total_candidates,
            "hires": hires,
            "avg_hire_time_days": avg_hire_time_days,
        },
        "pipeline": pipeline,
        "job_performance": job_performance,
        "time_saved_pct": time_saved_pct,
        "shortlist_accuracy_pct": shortlist_accuracy_pct,
        "ai_screening_pct": ai_screening_pct,
        "manual_screening_pct": manual_screening_pct,
        "clients": clients_list,
        "jobs_list": jobs_filter_list,
    }


def _empty_report(clients_list: list, jobs_filter_list: list) -> dict:
    pipeline = {k: 0 for k in ("new", "screened", "shortlisted", "interviewing", "selected", "hired", "rejected", "total")}
    return {
        "kpi": {"total_jobs": 0, "total_candidates": 0, "hires": 0, "avg_hire_time_days": 0},
        "pipeline": pipeline,
        "job_performance": [],
        "time_saved_pct": 0,
        "shortlist_accuracy_pct": 0,
        "ai_screening_pct": 0,
        "manual_screening_pct": 0,
        "clients": clients_list,
        "jobs_list": jobs_filter_list,
    }
