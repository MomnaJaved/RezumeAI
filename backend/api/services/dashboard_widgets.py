"""
Aggregated data for dashboard UI: applicant pipeline, jobs breakdown, candidate preview table.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, load_only

from api.models import Candidate, Job, JobCandidateRanking
from api.services.candidate_competition_score import compute_competition_payloads_for_list

_log = logging.getLogger("rezume.api")

_MAX_CAND_SCAN = 1200
_PREVIEW_ROWS = 10

# Pipeline: only columns needed for counts + avatars (avoid raw_text / embeddings).
_PIPELINE_COLUMNS = (
    Candidate.id,
    Candidate.external_id,
    Candidate.full_name,
    Candidate.status,
    Candidate.created_at,
)
# Preview table + profile percentiles among preview rows only (no cross-encoder).
_PREVIEW_COLUMNS = (
    Candidate.id,
    Candidate.external_id,
    Candidate.full_name,
    Candidate.role_label,
    Candidate.title,
    Candidate.status,
    Candidate.years_experience,
    Candidate.skills,
    Candidate.highest_degree,
    Candidate.certifications,
)

_PIPELINE_STAGES: list[tuple[str, str]] = [
    ("new", "New Applicants"),
    ("screened", "Screened"),
    ("shortlisted", "Short Listed"),
    ("interviewed", "Interviewed"),
    ("hired", "Hired"),
]

_PIE_COLORS = {
    "active": "#38bdf8",
    "completed": "#0ea5e9",
    "cancelled": "#075985",
    "on_hold": "#94a3b8",
}


def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if not parts:
        return "?"
    a = (parts[0][0] if parts[0] else "") + (parts[-1][0] if len(parts) > 1 and parts[-1] else "")
    return (a or "?").upper()[:2]


def _stage_key(status: str | None) -> str:
    s = (status or "new").strip().lower()
    if s in ("hired",):
        return "hired"
    if s in ("interviewing", "interview", "interviewed"):
        return "interviewed"
    if s in ("shortlisted", "selected"):
        return "shortlisted"
    if s in ("screened", "reviewed"):
        return "screened"
    if s in ("rejected", "not_a_fit", "reject"):
        return "screened"
    return "new"


def _status_label(status: str | None) -> str:
    s = (status or "new").strip()
    if not s:
        return "New"
    return s[0].upper() + s[1:].lower() if len(s) > 1 else s.upper()


def build_dashboard_widgets(db: Session) -> dict[str, Any]:
    try:
        candidates = (
            db.query(Candidate)
            .options(load_only(*_PIPELINE_COLUMNS))
            .order_by(Candidate.created_at.desc())
            .limit(_MAX_CAND_SCAN)
            .all()
        )
    except Exception as e:
        _log.warning("dashboard_widgets candidates: %s", e)
        candidates = []

    counts: dict[str, int] = {k: 0 for k, _ in _PIPELINE_STAGES}
    by_stage: dict[str, list[dict[str, str]]] = {k: [] for k, _ in _PIPELINE_STAGES}

    for c in candidates:
        sk = _stage_key(c.status)
        if sk not in counts:
            sk = "new"
        counts[sk] = counts.get(sk, 0) + 1
        if len(by_stage[sk]) < 8:
            by_stage[sk].append(
                {
                    "initials": _initials(c.full_name or c.external_id),
                    "external_id": c.external_id,
                    "name": (c.full_name or c.external_id).strip() or c.external_id,
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

    # --- Jobs pie: ranked vs not ranked (+ optional zero buckets for legend) ---
    total_jobs = db.query(Job).count()
    try:
        ranked_jobs = int(db.query(JobCandidateRanking.job_id).distinct().count())
    except Exception:
        ranked_jobs = 0
    on_hold = max(0, total_jobs - ranked_jobs)

    raw_segments = [
        ("active", "Active", ranked_jobs, _PIE_COLORS["active"]),
        ("on_hold", "On hold", on_hold, _PIE_COLORS["on_hold"]),
        ("completed", "Completed", 0, _PIE_COLORS["completed"]),
        ("cancelled", "Cancelled", 0, _PIE_COLORS["cancelled"]),
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

    # --- Candidate preview: profile-only scores among these rows (no CE × jobs pass). ---
    preview_raw = (
        db.query(Candidate)
        .options(load_only(*_PREVIEW_COLUMNS))
        .order_by(Candidate.created_at.desc())
        .limit(_PREVIEW_ROWS)
        .all()
    )
    scores: dict[UUID, dict[str, float]] = {}
    try:
        scores = dict(
            compute_competition_payloads_for_list(db, preview_raw, skip_job_breadth=True),
        )
    except Exception as e:
        _log.warning("dashboard_widgets scores: %s", e)

    candidate_rows: list[dict[str, Any]] = []
    for c in preview_raw:
        sc = scores.get(c.id, {})
        comp = int(round(float(sc.get("competition_score", 50.0))))
        role = (c.role_label or "").strip() or (c.title or "").strip() or "—"
        if len(role) > 32:
            role = role[:29] + "…"
        candidate_rows.append(
            {
                "external_id": c.external_id,
                "full_name": (c.full_name or c.external_id).strip() or c.external_id,
                "role": role,
                "score": max(0, min(100, comp)),
                "status": _status_label(c.status),
                "status_raw": (c.status or "new").strip().lower(),
            }
        )

    return {
        "pipeline": pipeline,
        "jobs_chart": pie,
        "candidate_preview": candidate_rows,
        "generated_at": datetime.utcnow().isoformat(),
    }
