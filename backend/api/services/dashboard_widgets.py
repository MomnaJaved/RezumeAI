"""
Aggregated data for dashboard UI: applicant pipeline, jobs breakdown, candidate preview table.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import exists
from sqlalchemy.orm import Session, load_only

from api.models import Candidate, Job, JobApplicant, JobCandidateRanking
from api.services.workspace_scope import candidate_visibility_predicate
from api.services.applicant_status_effective import (
    applicant_tracker_counts,
    effective_applicant_status,
    effective_candidate_status,
    global_applicant_status_created_pairs,
    recruiter_applicant_status_created_pairs,
    stage_bucket_for_dashboard,
)
from api.services.candidate_competition_score import compute_profile_scores_0_100
from api.services.candidate_display import display_full_name_from_db
from api.services.candidate_title_display import polish_candidate_title, polish_role_fine_display
from api.services.candidate_title_db import resolved_display_title

_log = logging.getLogger("rezume.api")


def _candidate_ids_applied_to_workspace_jobs(db: Session, workspace_id: UUID) -> list[UUID]:
    rows = (
        db.query(JobApplicant.candidate_id)
        .join(Job, Job.id == JobApplicant.job_id)
        .filter(Job.workspace_id == workspace_id)
        .distinct()
        .all()
    )
    return [r[0] for r in rows if r[0] is not None]


def _candidate_ids_visible_to_workspace(db: Session, workspace_id: UUID) -> list[UUID]:
    """
    Every candidate a recruiter's workspace should see on the dashboard:
    applicants/rankings/shortlist on workspace jobs, plus profiles uploaded
    directly into the workspace (``Candidate.workspace_id``). Without the
    second set, freshly uploaded candidates would disappear from the
    dashboard cohort until they were attached to a job.
    """
    rows = (
        db.query(Candidate.id)
        .filter(candidate_visibility_predicate(workspace_id))
        .all()
    )
    return [r[0] for r in rows if r[0] is not None]


def _candidates_by_ids_ordered(db: Session, cand_ids: list[UUID], *, columns_only: bool, limit: int) -> list[Candidate]:
    if not cand_ids:
        return []
    uniq: list[UUID] = []
    seen: set[UUID] = set()
    for cid in cand_ids:
        if cid not in seen:
            seen.add(cid)
            uniq.append(cid)
    q = db.query(Candidate)
    if columns_only:
        q = q.options(load_only(*_PIPELINE_COLUMNS))
    out: list[Candidate] = []
    for i in range(0, len(uniq), _CAND_ID_IN_CHUNK):
        chunk = uniq[i : i + _CAND_ID_IN_CHUNK]
        out.extend(q.filter(Candidate.id.in_(chunk)).all())
    out.sort(key=lambda c: c.created_at or datetime.min, reverse=True)
    return out[:limit]


# Cap for *preview avatars* / recent applicant scan only. Pipeline **counts** must include every row.
_MAX_PIPELINE_PREVIEW_APPLICANTS = 1200
_MAX_CANDIDATE_PREVIEW_POOL = 1200
_CAND_ID_IN_CHUNK = 800
_PREVIEW_ROWS = 5

# Pipeline: only columns needed for counts + avatars (avoid raw_text / embeddings).
_PIPELINE_COLUMNS = (
    Candidate.id,
    Candidate.external_id,
    Candidate.full_name,
    Candidate.status,
    Candidate.created_at,
)
_PIPELINE_STAGES: list[tuple[str, str]] = [
    ("new", "New Applicants"),
    ("screened", "Screened"),
    ("shortlisted", "Short Listed"),
    ("interviewing", "Interviewing"),
    ("rejected", "Rejected"),
    ("hired", "Hired"),
]

_PIE_COLORS = {
    # Keep within the site's blue/teal palette (matches `cand-add-btn` accent).
    "active": "#6ce5e8",
    "completed": "#41b8d5",
    "cancelled": "#2d8bba",
    "on_hold": "#506e9a",
}


def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if not parts:
        return "?"
    a = (parts[0][0] if parts[0] else "") + (parts[-1][0] if len(parts) > 1 and parts[-1] else "")
    return (a or "?").upper()[:2]


def _stage_key_for_applicant(stored_status: str | None, candidate_created_at) -> str:
    eff = effective_applicant_status(stored_status, candidate_created_at)
    return stage_bucket_for_dashboard(eff)


def _bulk_candidate_created_at(db: Session, cand_ids: set[UUID]) -> dict[UUID, datetime | None]:
    """Map candidate id -> created_at for TTL rules (chunked for SQLite IN limits)."""
    if not cand_ids:
        return {}
    out: dict[UUID, datetime | None] = {}
    ids = list(cand_ids)
    for i in range(0, len(ids), _CAND_ID_IN_CHUNK):
        chunk = ids[i : i + _CAND_ID_IN_CHUNK]
        for cid, cat in db.query(Candidate.id, Candidate.created_at).filter(Candidate.id.in_(chunk)).all():
            out[cid] = cat
    return out


def _candidates_pipeline_columns_bulk(db: Session, cand_ids: list[UUID]) -> dict[UUID, Candidate]:
    if not cand_ids:
        return {}
    out: dict[UUID, Candidate] = {}
    for i in range(0, len(cand_ids), _CAND_ID_IN_CHUNK):
        chunk = cand_ids[i : i + _CAND_ID_IN_CHUNK]
        for c in (
            db.query(Candidate)
            .options(load_only(*_PIPELINE_COLUMNS))
            .filter(Candidate.id.in_(chunk))
            .all()
        ):
            out[c.id] = c
    return out


def _status_label(status: str | None) -> str:
    s = (status or "new").strip()
    if not s:
        return "New"
    return s[0].upper() + s[1:].lower() if len(s) > 1 else s.upper()


def _preview_rows_for_cohort(
    preview: list[Candidate],
    profile_by_id: dict[UUID, float],
    job_fit_by_id: dict[UUID, float],
) -> list[dict[str, Any]]:
    candidate_rows: list[dict[str, Any]] = []
    for c in preview[:_PREVIEW_ROWS]:
        p = float(profile_by_id.get(c.id, 50.0))
        j = float(job_fit_by_id.get(c.id, 0.0))
        candidate_rows.append(
            {
                "id": str(c.id),
                "external_id": c.external_id,
                "full_name": display_full_name_from_db(c.full_name),
                "title": polish_candidate_title(resolved_display_title(c)),
                "role_fine": polish_role_fine_display((getattr(c, "role_fine", None) or "").strip()),
                "profile_strength": max(0, min(100, int(round(p)))),
                "avg_job_fit": max(0, min(100, int(round(j)))),
                "best_job_match": max(0, min(100, int(round(j)))),
                "status": _status_label(effective_candidate_status(c.status, c.created_at)),
                "status_raw": effective_candidate_status(c.status, c.created_at).strip().lower(),
                "email": (getattr(c, "contact_email", None) or "").strip(),
            }
        )
    return candidate_rows




def build_dashboard_widgets(db: Session, recruiter_workspace_id: Optional[UUID] = None) -> dict[str, Any]:
    # Without recruiter_workspace_id: global tracker (legacy / REQUIRE_AUTH off).
    # With recruiter_workspace_id: only applications to jobs in that workspace.
    stage_order = [k for k, _ in _PIPELINE_STAGES]
    try:
        if recruiter_workspace_id is not None:
            pairs = recruiter_applicant_status_created_pairs(db, recruiter_workspace_id)
        else:
            pairs = global_applicant_status_created_pairs(db)
        agg = applicant_tracker_counts(pairs)
        counts: dict[str, int] = {k: int(agg.get(k, 0)) for k in stage_order}
    except Exception as e:
        _log.warning("dashboard_widgets pipeline aggregate: %s", e)
        counts = {k: 0 for k in stage_order}

    by_stage: dict[str, list[dict[str, Any]]] = {k: [] for k, _ in _PIPELINE_STAGES}
    first_by_stage: dict[str, Candidate] = {}

    # Avatars / "people" chips: keep a bounded recent scan for responsiveness.
    try:
        q = db.query(JobApplicant)
        if recruiter_workspace_id is not None:
            q = q.join(Job, Job.id == JobApplicant.job_id).filter(Job.workspace_id == recruiter_workspace_id)
        apps_preview = q.order_by(JobApplicant.updated_at.desc()).limit(_MAX_PIPELINE_PREVIEW_APPLICANTS).all()
    except Exception as e:
        _log.warning("dashboard_widgets applicants(preview): %s", e)
        apps_preview = []

    preview_cand_ids = list({a.candidate_id for a in apps_preview if getattr(a, "candidate_id", None)})
    created_by_id = _bulk_candidate_created_at(db, set(preview_cand_ids))
    cand_by_id = _candidates_pipeline_columns_bulk(db, preview_cand_ids)

    for a in apps_preview:
        cid = getattr(a, "candidate_id", None)
        c0 = cand_by_id.get(cid) if cid else None
        cat = (created_by_id.get(cid) if cid else None) or (c0.created_at if c0 else None)
        sk = _stage_key_for_applicant(getattr(a, "status", None), cat)
        c = c0
        if c and sk in stage_order and sk not in first_by_stage:
            first_by_stage[sk] = c
        if c and len(by_stage[sk]) < 8:
            by_stage[sk].append(
                {
                    "id": str(c.id),
                    "initials": _initials(display_full_name_from_db(c.full_name)),
                    "external_id": c.external_id,
                    "name": display_full_name_from_db(c.full_name),
                }
            )

    # Profile-only candidates (no JobApplicant row): surface them in the
    # pipeline preview too, so a fresh upload shows up under "New Applicants"
    # before it's been attached to a job.
    #   - Global dashboard (no workspace): every candidate without a job link.
    #   - Recruiter dashboard: only the recruiter's *own* workspace-owned
    #     orphans; we must not spill candidates from other tenants here even
    #     if they happen to have no applicant rows anywhere.
    orphan_cands: list[Candidate] = []
    try:
        has_app = exists().where(JobApplicant.candidate_id == Candidate.id)
        oq = (
            db.query(Candidate)
            .options(load_only(*_PIPELINE_COLUMNS))
            .filter(~has_app)
        )
        if recruiter_workspace_id is not None:
            oq = oq.filter(Candidate.workspace_id == recruiter_workspace_id)
        orphan_cands = oq.order_by(Candidate.created_at.desc()).limit(500).all()
    except Exception as e:
        _log.warning("dashboard_widgets orphan pipeline preview: %s", e)
        orphan_cands = []

    for c in orphan_cands:
        sk = _stage_key_for_applicant(c.status, c.created_at)
        if sk not in stage_order:
            continue
        if sk not in first_by_stage:
            first_by_stage[sk] = c
        if len(by_stage[sk]) < 8:
            by_stage[sk].append(
                {
                    "id": str(c.id),
                    "initials": _initials(display_full_name_from_db(c.full_name)),
                    "external_id": c.external_id,
                    "name": display_full_name_from_db(c.full_name),
                }
            )

    pipeline: list[dict[str, Any]] = []
    for key, label in _PIPELINE_STAGES:
        pipeline.append(
            {
                "key": key,
                "label": label,
                "count": counts.get(key, 0),
                "people": by_stage.get(key, []),
            }
        )

    # --- Jobs pie: lifecycle status breakdown ---
    jq = db.query(Job)
    if recruiter_workspace_id is not None:
        jq = jq.filter(Job.workspace_id == recruiter_workspace_id)
    total_jobs = int(jq.count())
    by_status = {"active": 0, "on_hold": 0, "completed": 0, "cancelled": 0}
    try:
        rows = jq.with_entities(Job.status).all()
        for (st,) in rows:
            s = (st or "active").strip().lower()
            if s == "inactive":
                s = "on_hold"
            if s in by_status:
                by_status[s] += 1
    except Exception:
        pass

    raw_segments = [
        ("active", "Active", by_status["active"], _PIE_COLORS["active"]),
        ("on_hold", "On hold", by_status["on_hold"], _PIE_COLORS["on_hold"]),
        ("completed", "Completed", by_status["completed"], _PIE_COLORS["completed"]),
        ("cancelled", "Cancelled", by_status["cancelled"], _PIE_COLORS["cancelled"]),
    ]
    nonzero = [(k, lab, n, col) for k, lab, n, col in raw_segments if n > 0]
    if not nonzero and total_jobs == 0:
        pie = {
            "segments": [
                {
                    "key": "empty",
                    "label": "No jobs yet",
                    "count": 0,
                    "pct": 100.0,
                    "color": "#334155",
                }
            ],
            "total": 0,
        }
    else:
        total_n = sum(n for _, _, n, _ in nonzero)
        segments = []
        for k, lab, n, col in nonzero:
            pct = round(1000.0 * n / total_n) / 10.0 if total_n else 0.0
            segments.append({"key": k, "label": lab, "count": n, "pct": pct, "color": col})
        pie = {"segments": segments, "total": total_jobs}

    # --- Candidate preview: cohort for profile percentiles ---
    try:
        if recruiter_workspace_id is not None:
            ids = _candidate_ids_visible_to_workspace(db, recruiter_workspace_id)
            cohort = _candidates_by_ids_ordered(db, ids, columns_only=False, limit=_MAX_CANDIDATE_PREVIEW_POOL)
        else:
            cohort = db.query(Candidate).order_by(Candidate.created_at.desc()).all()
    except Exception as e:
        _log.warning("dashboard_widgets cohort for scores: %s", e)
        cohort = []

    # Profile strength is cohort-relative; job fit is model-based vs jobs. Compute job fit only for preview rows.
    profile_by_id: dict[UUID, float] = {}
    job_fit_by_id: dict[UUID, float] = {}
    try:
        prof = compute_profile_scores_0_100(cohort) if cohort else []
        profile_by_id = {c.id: prof[i] for i, c in enumerate(cohort)}
    except Exception as e:
        _log.warning("dashboard_widgets profile scores: %s", e)

    # Candidate preview remains based on candidate recency + stages (best-effort).
    try:
        if recruiter_workspace_id is not None:
            ids = _candidate_ids_visible_to_workspace(db, recruiter_workspace_id)
            candidates = _candidates_by_ids_ordered(db, ids, columns_only=True, limit=_MAX_CANDIDATE_PREVIEW_POOL)
        else:
            candidates = (
                db.query(Candidate)
                .options(load_only(*_PIPELINE_COLUMNS))
                .order_by(Candidate.created_at.desc())
                .limit(_MAX_CANDIDATE_PREVIEW_POOL)
                .all()
            )
    except Exception as e:
        _log.warning("dashboard_widgets candidates: %s", e)
        candidates = []

    preview: list[Candidate] = []
    seen: set[UUID] = set()
    for k in stage_order:
        c = first_by_stage.get(k)
        if c and c.id not in seen:
            preview.append(c)
            seen.add(c.id)
        if len(preview) >= _PREVIEW_ROWS:
            break
    if len(preview) < _PREVIEW_ROWS:
        for c in candidates:
            if c.id in seen:
                continue
            preview.append(c)
            seen.add(c.id)
            if len(preview) >= _PREVIEW_ROWS:
                break

    # Dashboard should be fast: use cached best match score stored on Candidate rows.
    job_fit_by_id = {c.id: float(getattr(c, "best_job_match_score", 0.0) or 0.0) for c in preview}

    candidate_rows = _preview_rows_for_cohort(preview, profile_by_id, job_fit_by_id)

    return {
        "pipeline": pipeline,
        "jobs_chart": pie,
        "candidate_preview": candidate_rows,
        "generated_at": datetime.utcnow().isoformat(),
        # Preview table intentionally does not wait on cross-encoder job breadth; list uses profile field.
        "needs_job_breadth_scores_refresh": False,
    }


def build_dashboard_preview_job_breadth_scores(db: Session, recruiter_workspace_id: Optional[UUID] = None) -> dict[str, Any]:
    """
    Same candidate preview rows as GET /meta/dashboard/widgets (profile cohort scores for the table).
    Kept for API compatibility; does not run the cross-encoder job-breadth pass.
    """
    try:
        if recruiter_workspace_id is not None:
            ids = _candidate_ids_visible_to_workspace(db, recruiter_workspace_id)
            cohort = _candidates_by_ids_ordered(db, ids, columns_only=False, limit=_MAX_CANDIDATE_PREVIEW_POOL)
        else:
            cohort = db.query(Candidate).order_by(Candidate.created_at.desc()).all()
    except Exception as e:
        _log.warning("dashboard_preview_job_breadth cohort: %s", e)
        cohort = []

    profile_by_id: dict[UUID, float] = {}
    try:
        prof = compute_profile_scores_0_100(cohort) if cohort else []
        profile_by_id = {c.id: prof[i] for i, c in enumerate(cohort)}
    except Exception as e:
        _log.warning("dashboard_preview_job_breadth profile scores: %s", e)

    # Even when skipping job-breadth scoring, the preview table expects a job-fit value.
    # Use cached best-match score from Candidate rows as a fast fallback.
    job_fit_by_id = {c.id: float(getattr(c, "best_job_match_score", 0.0) or 0.0) for c in cohort}

    return {
        "candidate_preview": _preview_rows_for_cohort(cohort, profile_by_id, job_fit_by_id),
        "generated_at": datetime.utcnow().isoformat(),
    }
