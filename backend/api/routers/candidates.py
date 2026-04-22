from __future__ import annotations

import mimetypes
from typing import Optional
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from fastapi import Response
from fastapi import Body
from fastapi.responses import FileResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_current_user_optional, require_user_if_auth_enabled
from api.models import Candidate, Client, Job, JobApplicant, JobCandidateRanking, JobCandidateSbertScore, RecruiterCandidateHidden, User
from api.schemas import CandidateCreate, CandidateRead, CandidateReadWithScores, CandidateUpdate
from api.services.activity_log import log_activity
from api.services.candidate_best_job_cache import refresh_candidate_best_job_cache, workspace_best_scores
from api.services.candidate_competition_score import compute_competition_payloads_for_list
from api.services.candidate_serialization import candidate_read_dict, resolve_candidate_headline
from api.services.applicant_status_effective import STORAGE_APPLICANT_STATUSES, effective_applicant_status, sync_candidate_status_from_applicants
from api.services.workspace_scope import candidate_query_filtered_for_workspace, ensure_workspace_for_recruiter

router = APIRouter(prefix="/candidates", tags=["candidates"])

# PATCH body: only these ORM columns may be updated (avoid stray keys / typos).
_CANDIDATE_PATCHABLE_KEYS = frozenset(
    {
        "full_name",
        "title",
        "role_label",
        "role_fine",
        "skills",
        "years_experience",
        "highest_degree",
        "certifications",
        "education_lines",
        "status",
        "contact_email",
    }
)
# DB columns are non-null strings; clients sometimes send JSON null — coerce before setattr.
_CANDIDATE_PATCH_STRING_KEYS = frozenset(
    {
        "full_name",
        "title",
        "role_label",
        "role_fine",
        "skills",
        "highest_degree",
        "certifications",
        "education_lines",
        "status",
        "contact_email",
    }
)


def _ensure_candidate_self_or_recruiter(c: Candidate, user: Optional[User]) -> None:
    if user is None:
        return
    if getattr(user, "account_role", "recruiter") == "candidate":
        if getattr(c, "user_id", None) != user.id:
            raise HTTPException(status_code=403, detail="You can only access your own candidate profile")


def _ensure_recruiter_sees_candidate(db: Session, c: Candidate, user: Optional[User]) -> None:
    if user is None or getattr(user, "account_role", "") == "candidate":
        return
    w = ensure_workspace_for_recruiter(db, user)
    if w is None:
        return
    q = candidate_query_filtered_for_workspace(db.query(Candidate).filter(Candidate.id == c.id), w)
    if q.first() is None:
        raise HTTPException(status_code=404, detail="Candidate not found")


def _best_job_enrichment_map(db: Session, job_external_ids: set[str]) -> dict[str, dict[str, str]]:
    """
    Batch lookup for best_job_external_id -> job + client display fields.
    """
    ids = [x for x in job_external_ids if x]
    if not ids:
        return {}
    rows = (
        db.query(Job, Client)
        .outerjoin(Client, Client.id == Job.client_id)
        .filter(Job.external_id.in_(ids))
        .all()
    )
    out: dict[str, dict[str, str]] = {}
    for j, cl in rows:
        ext = (getattr(j, "external_id", "") or "").strip()
        if not ext:
            continue
        out[ext] = {
            "title": (j.title or "").strip(),
            "department": (j.department or "").strip(),
            "client_name": (cl.name or "").strip() if cl else "",
            "client_company": (cl.company_name or "").strip() if cl else "",
            "client_contact": (cl.contact_person or "").strip() if cl else "",
            "client_email": (cl.email or "").strip() if cl else "",
        }
    return out


def _serialize_candidate_read(
    db: Session,
    c: Candidate,
    *,
    enrich: dict[str, str | None] | None = None,
    ws_score: "tuple[float, str] | None" = None,
    recruiter_scoped: bool = False,
) -> CandidateRead:
    d = candidate_read_dict(c)
    if ws_score is not None:
        # Recruiter has a workspace-specific score for this candidate.
        d["best_job_match_score"] = ws_score[0] if ws_score[0] >= 0 else None
        d["best_job_external_id"] = ws_score[1]
    elif recruiter_scoped:
        # Recruiter context but no workspace score yet — clear the globally-cached
        # value so this recruiter cannot see a score produced by a different
        # recruiter's matching run.
        d["best_job_match_score"] = None
        d["best_job_external_id"] = ""
    # else: non-recruiter view (candidate portal, no auth) — keep the global cache.
    jid = (d.get("best_job_external_id") or "").strip()
    if jid and enrich:
        d.update({k: v for k, v in enrich.items() if v is not None})
    return CandidateRead.model_validate(d)


@router.get("", response_model=list[CandidateRead])
def list_candidates(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    w = None
    q = db.query(Candidate).filter(or_(Candidate.status.is_(None), func.lower(Candidate.status) != "hired"))
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            q = candidate_query_filtered_for_workspace(q, w)
    rows = q.order_by(Candidate.created_at.desc()).offset(skip).limit(limit).all()
    ws_scores = workspace_best_scores(db, w, [c.id for c in rows]) if w is not None else {}
    is_recruiter = w is not None
    return [_serialize_candidate_read(db, c, ws_score=ws_scores.get(c.id), recruiter_scoped=is_recruiter) for c in rows]


@router.get("/page")
def list_candidates_page(
    skip: int = 0,
    limit: int = Query(50, ge=1, le=100),
    q: str = "",
    status: str = "",
    role: str = "",
    sort: str = "created_desc",
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Server-side paginated candidates listing with lightweight filters.
    Returns: { total, items }.
    """
    needle = (q or "").strip()
    st = (status or "").strip().lower()
    rl = (role or "").strip().lower()
    srt = (sort or "created_desc").strip().lower()

    w = None
    base = db.query(Candidate).filter(or_(Candidate.status.is_(None), func.lower(Candidate.status) != "hired"))
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            base = candidate_query_filtered_for_workspace(base, w)
    if needle:
        like = f"%{needle}%"
        base = base.filter(
            or_(
                Candidate.full_name.ilike(like),
                Candidate.title.ilike(like),
                Candidate.skills.ilike(like),
                Candidate.filename.ilike(like),
                Candidate.contact_email.ilike(like),
                Candidate.external_id.ilike(like),
            )
        )
    if st:
        base = base.filter(Candidate.status.ilike(st))
    if rl:
        base = base.filter(Candidate.role_label.ilike(rl))

    total = int(base.count())

    if srt == "name_asc":
        base = base.order_by(Candidate.full_name.asc())
    elif srt == "score_desc":
        base = base.order_by(Candidate.best_job_match_score.desc().nullslast(), Candidate.created_at.desc())
    else:
        base = base.order_by(Candidate.created_at.desc())

    rows = base.offset(max(0, int(skip or 0))).limit(int(limit)).all()

    # Workspace-specific scores: each recruiter sees only scores from their own
    # matching runs, regardless of what other recruiters scored for the same candidate.
    ws_scores = workspace_best_scores(db, w, [r.id for r in rows]) if w is not None else {}

    # If rankings exist but best_job_match_score was never refreshed (e.g. older saves), recompute cache.
    need_heal = [r.id for r in rows if getattr(r, "best_job_match_score", None) is None]
    if need_heal:
        ranked_ids = {
            cid
            for (cid,) in db.query(JobCandidateRanking.candidate_id)
            .filter(JobCandidateRanking.candidate_id.in_(need_heal))
            .distinct()
            .all()
        }
        fix_ids = [cid for cid in need_heal if cid in ranked_ids]
        if fix_ids:
            refresh_candidate_best_job_cache(db, fix_ids)
            fix_set = set(fix_ids)
            for r in rows:
                if r.id in fix_set:
                    db.refresh(r)

    # Enrich with job metadata using the workspace-specific best job (may differ
    # from the globally-cached best_job_external_id on the Candidate row).
    job_ids: set[str] = set()
    for r in rows:
        ws = ws_scores.get(r.id)
        jid = ws[1] if ws else (getattr(r, "best_job_external_id", "") or "").strip()
        if jid:
            job_ids.add(jid)
    enrich_by_job = _best_job_enrichment_map(db, job_ids)

    items: list[CandidateRead] = []
    for r in rows:
        ws = ws_scores.get(r.id)
        jid = ws[1] if ws else (getattr(r, "best_job_external_id", "") or "").strip()
        extra = enrich_by_job.get(jid, {}) if jid else {}
        mapped = {
            "best_job_title": extra.get("title") or None,
            "best_job_department": extra.get("department") or None,
            "best_job_client_name": extra.get("client_name") or None,
            "best_job_client_company": extra.get("client_company") or None,
            "best_job_client_contact": extra.get("client_contact") or None,
            "best_job_client_email": extra.get("client_email") or None,
        }
        items.append(_serialize_candidate_read(db, r, enrich=mapped if jid else None, ws_score=ws, recruiter_scoped=w is not None))
    return {"total": total, "items": items}


@router.get("/scoreboard", response_model=list[CandidateReadWithScores])
def list_candidates_scoreboard(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    **Candidates page only:** cohort-relative profile percentiles plus mean cross-encoder match
    vs all jobs in the DB. Expensive; do not use for generic listing.
    Set REZUME_COMPETITION_SKIP_JOB_FIT=1 to skip the job pass (profile only).
    """
    # Hard cap to prevent pathological slow requests; frontend should paginate.
    limit = max(1, min(int(limit or 50), 100))
    skip = max(0, int(skip or 0))
    w = None
    cq = db.query(Candidate)
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            cq = candidate_query_filtered_for_workspace(cq, w)
    page = cq.order_by(Candidate.created_at.desc()).offset(skip).limit(limit).all()

    # Workspace-specific best scores: each recruiter sees scores from their own
    # matching runs only, not scores generated by other recruiters.
    ws_scores = workspace_best_scores(db, w, [c.id for c in page]) if w is not None else {}

    out: list[CandidateReadWithScores] = []
    for c in page:
        base = candidate_read_dict(c)
        p = 0.0
        j = 0.0
        ws = ws_scores.get(c.id)
        if ws is not None:
            # Workspace-specific score found.
            b = ws[0]
            bj = ws[1] or None
        elif w is not None:
            # Recruiter context but no workspace score yet — do not show the global
            # cached value which may belong to a different recruiter's run.
            b = 0.0
            bj = None
        else:
            # Non-recruiter view (candidate portal, no auth) — use global cache.
            b = float(getattr(c, "best_job_match_score", 0.0) or 0.0)
            bj = (getattr(c, "best_job_external_id", "") or "").strip() or None
        # Write the workspace-scoped (or cleared) score into base before construction
        # so there are no duplicate keyword arguments when unpacking **base.
        base["best_job_match_score"] = b if b else None
        base["best_job_external_id"] = bj or ""
        out.append(
            CandidateReadWithScores(
                **base,
                profile_percentile_score=p,
                avg_job_match_score=j,
                competition_score=p,
            )
        )
    return out


@router.get("/by-external/{external_id}", response_model=CandidateRead)
def get_candidate_by_external_id(
    external_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    c = db.query(Candidate).filter(Candidate.external_id == external_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_recruiter_sees_candidate(db, c, user)
    w = None
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
    ws = workspace_best_scores(db, w, [c.id]).get(c.id) if w is not None else None
    jid = ws[1] if ws else (getattr(c, "best_job_external_id", "") or "").strip()
    extra = _best_job_enrichment_map(db, {jid}).get(jid, {}) if jid else {}
    mapped = {
        "best_job_title": extra.get("title") or None,
        "best_job_department": extra.get("department") or None,
        "best_job_client_name": extra.get("client_name") or None,
        "best_job_client_company": extra.get("client_company") or None,
        "best_job_client_contact": extra.get("client_contact") or None,
        "best_job_client_email": extra.get("client_email") or None,
    }
    return _serialize_candidate_read(db, c, enrich=mapped if jid else None, ws_score=ws, recruiter_scoped=w is not None)


@router.get("/by-external/{external_id}/file")
def download_candidate_file(
    external_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    c = db.query(Candidate).filter(Candidate.external_id == external_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_recruiter_sees_candidate(db, c, user)
    p = Path((getattr(c, "storage_path", "") or "").strip())
    if not p or not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="Resume file not found")
    filename = (c.filename or p.name).split("/")[-1]
    media_type, _ = mimetypes.guess_type(filename)
    if not media_type:
        media_type = "application/octet-stream"
    return FileResponse(
        path=str(p),
        filename=filename,
        media_type=media_type,
        content_disposition_type="inline",
    )


@router.get("/{candidate_uuid}/with-scores", response_model=CandidateReadWithScores)
def get_candidate_with_scores(
    candidate_uuid: UUID,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """Full candidate row plus competition scores (same computation as GET /candidates/scoreboard)."""
    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_candidate_self_or_recruiter(c, user)
    _ensure_recruiter_sees_candidate(db, c, user)
    w = None
    cohort_q = db.query(Candidate)
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            cohort_q = candidate_query_filtered_for_workspace(cohort_q, w)
    cohort = cohort_q.order_by(Candidate.created_at.desc()).all()
    # One candidate at a time: do not re-run job-breadth for the entire workspace (can be
    # thousands of cross-encoder batches and will hang the dev proxy with "socket hang up").
    base = candidate_read_dict(c)
    extra = compute_competition_payload_for_one_in_cohort(db, c, cohort)
    ws = workspace_best_scores(db, w, [c.id]).get(c.id) if w is not None else None
    if ws is not None:
        # Recruiter has a workspace-specific score — use it.
        base["best_job_match_score"] = ws[0]
        base["best_job_external_id"] = ws[1] or ""
    elif w is not None:
        # Recruiter context but no workspace score yet — hide the globally-cached
        # value so this recruiter cannot see a score produced by a different
        # recruiter's matching run.
        base["best_job_match_score"] = None
        base["best_job_external_id"] = ""
    # else: non-recruiter view (candidate portal) — keep global cache already in base.
    return CandidateReadWithScores(
        **base,
        profile_percentile_score=extra["profile_percentile_score"],
        avg_job_match_score=extra["avg_job_match_score"],
        competition_score=extra["competition_score"],
    )


@router.get("/{candidate_uuid}/top-matches")
def candidate_top_matches(
    candidate_uuid: UUID,
    limit: int = 3,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Top job matches for a candidate across all jobs based on stored rankings.
    Does NOT compute any new model scores; it reads the existing matches table.
    """
    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_candidate_self_or_recruiter(c, user)
    _ensure_recruiter_sees_candidate(db, c, user)
    lim = max(1, min(int(limit or 3), 20))
    rq = (
        db.query(JobCandidateRanking, Job)
        .join(Job, Job.id == JobCandidateRanking.job_id)
        .filter(JobCandidateRanking.candidate_id == c.id)
    )
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            # Filter by both the job's workspace AND the ranking's workspace so that
            # scores generated by a different recruiter's run never appear here.
            # NULL workspace_id rows (legacy pre-isolation data) are accepted only
            # when the job itself belongs to this recruiter's workspace.
            rq = rq.filter(
                Job.workspace_id == w,
                or_(
                    JobCandidateRanking.workspace_id == w,
                    JobCandidateRanking.workspace_id.is_(None),
                ),
            )
    rows = rq.order_by(JobCandidateRanking.cross_encoder_score.desc()).limit(lim).all()
    items = []
    for r, j in rows:
        items.append(
            {
                "job_external_id": j.external_id,
                "job_title": j.title,
                "job_status": j.status,
                "score": float(r.cross_encoder_score or 0.0),
                "rank_position": int(r.rank_position or 0),
            }
        )
    return {"candidate_id": str(c.id), "items": items}


@router.get("/{candidate_uuid}/matches")
def candidate_matches(
    candidate_uuid: UUID,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Latest persisted match scores for a candidate across all jobs.
    Always reads from job_candidate_rankings — never recomputes.
    Returns scores sorted descending so the best match is first.
    """
    import json as _json

    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_candidate_self_or_recruiter(c, user)
    _ensure_recruiter_sees_candidate(db, c, user)
    lim = max(1, min(int(limit or 20), 100))
    mq = (
        db.query(JobCandidateRanking, Job)
        .join(Job, Job.id == JobCandidateRanking.job_id)
        .filter(JobCandidateRanking.candidate_id == c.id)
    )
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            mq = mq.filter(
                Job.workspace_id == w,
                or_(
                    JobCandidateRanking.workspace_id == w,
                    JobCandidateRanking.workspace_id.is_(None),
                ),
            )
    rows = mq.order_by(JobCandidateRanking.cross_encoder_score.desc()).limit(lim).all()
    items = []
    for r, j in rows:
        expl = None
        raw_expl = getattr(r, "explanation_json", None) or ""
        if raw_expl:
            try:
                expl = _json.loads(raw_expl)
            except Exception:
                expl = None
        items.append(
            {
                "job_external_id": j.external_id,
                "job_title": (j.title or "").strip(),
                "job_status": (j.status or "").strip(),
                "match_score": float(r.cross_encoder_score or 0.0),
                "sbert_similarity": float(r.sbert_similarity or 0.0),
                "rank_position": int(r.rank_position or 0),
                "run_at": r.run_at.isoformat() if r.run_at else None,
                "explanation": expl,
            }
        )
    best_score = max((it["match_score"] for it in items), default=None)
    return {
        "candidate_id": str(c.id),
        "candidate_external_id": c.external_id,
        "best_match_score": best_score,
        "items": items,
    }


@router.get("/{candidate_uuid}/job-evaluations")
def candidate_job_evaluations(
    candidate_uuid: UUID,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Per-job evaluation transparency: retrieval (SBERT) and cross-encoder scores when present,
    even when the candidate did not reach the final ranked shortlist.
    """
    import json

    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_recruiter_sees_candidate(db, c, user)
    w = None
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)

    by_job: dict = {}

    def ensure_row(job: Job) -> dict:
        jid = str(job.id)
        if jid not in by_job:
            by_job[jid] = {
                "job_external_id": job.external_id,
                "job_title": job.title or "",
                "applicant_status": None,
                "applicant_status_effective": None,
                "retrieval_similarity": None,
                "cross_encoder_score": None,
                "rank_position": None,
                "in_saved_ranking": False,
                "brief_reason": None,
            }
        return by_job[jid]

    app_q = (
        db.query(JobApplicant, Job)
        .join(Job, Job.id == JobApplicant.job_id)
        .filter(JobApplicant.candidate_id == c.id)
    )
    if w is not None:
        app_q = app_q.filter(Job.workspace_id == w)
    for app, job in app_q.all():
        row = ensure_row(job)
        st = (app.status or "new").strip().lower()
        row["applicant_status"] = st
        row["applicant_status_effective"] = effective_applicant_status(st, c.created_at)

    sb_q = (
        db.query(JobCandidateSbertScore, Job)
        .join(Job, Job.id == JobCandidateSbertScore.job_id)
        .filter(JobCandidateSbertScore.candidate_id == c.id)
    )
    if w is not None:
        sb_q = sb_q.filter(Job.workspace_id == w)
    for sb, job in sb_q.all():
        row = ensure_row(job)
        row["retrieval_similarity"] = float(sb.cosine_similarity or 0.0)

    rnk_q = (
        db.query(JobCandidateRanking, Job)
        .join(Job, Job.id == JobCandidateRanking.job_id)
        .filter(JobCandidateRanking.candidate_id == c.id)
    )
    if w is not None:
        rnk_q = rnk_q.filter(
            Job.workspace_id == w,
            or_(
                JobCandidateRanking.workspace_id == w,
                JobCandidateRanking.workspace_id.is_(None),
            ),
        )
    for rnk, job in rnk_q.all():
        row = ensure_row(job)
        row["cross_encoder_score"] = float(rnk.cross_encoder_score or 0.0)
        row["rank_position"] = int(rnk.rank_position or 0)
        row["in_saved_ranking"] = True
        raw = getattr(rnk, "explanation_json", None) or ""
        if raw:
            try:
                expl = json.loads(raw)
                parts = []
                for k in ("skills_match_ratio", "experience_match", "education_match"):
                    if k in expl and expl[k] is not None:
                        parts.append(f"{k.replace('_', ' ')}: {float(expl[k]):.2f}")
                row["brief_reason"] = "; ".join(parts) if parts else None
            except Exception:
                row["brief_reason"] = None

    items = sorted(by_job.values(), key=lambda x: (x.get("cross_encoder_score") or 0.0), reverse=True)
    return {"candidate_id": str(c.id), "candidate_external_id": c.external_id, "items": items}


@router.patch("/{external_id}/status")
def set_candidate_status(
    external_id: str,
    body: dict,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Dedicated, single-purpose endpoint for changing a candidate's pipeline status.
    This is the canonical way to update status from the Matching Tab and any other UI.
    Only explicit user actions should call this endpoint — AI/ranking logic must not.
    """
    st = str(body.get("status") or "").strip().lower()
    if st not in STORAGE_APPLICANT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of: {', '.join(sorted(STORAGE_APPLICANT_STATUSES))}",
        )
    c = db.query(Candidate).filter(Candidate.external_id == external_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_recruiter_sees_candidate(db, c, user)
    c.status = st
    # Mirror to all job_applicants rows so per-job views stay consistent.
    now = datetime.utcnow()
    for app in db.query(JobApplicant).filter(JobApplicant.candidate_id == c.id).all():
        app.status = st
        app.updated_at = now
    db.commit()
    return {"external_id": external_id, "status": st}


@router.patch("/{candidate_uuid}", response_model=CandidateRead)
def patch_candidate(
    candidate_uuid: UUID,
    body: CandidateUpdate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_candidate_self_or_recruiter(c, user)
    _ensure_recruiter_sees_candidate(db, c, user)
    upd = body.model_dump(exclude_unset=True)
    if "status" in upd and upd["status"] is not None:
        upd["status"] = str(upd["status"]).strip()[:64] or "new"
    if "role_fine" in upd and upd["role_fine"] is not None:
        upd["role_fine"] = str(upd["role_fine"]).strip()[:64] or "unknown"
    if "contact_email" in upd and upd["contact_email"] is not None:
        upd["contact_email"] = str(upd["contact_email"]).strip()[:320]
    for k in _CANDIDATE_PATCH_STRING_KEYS:
        if k in upd and upd[k] is None:
            upd[k] = ""
    for key, val in upd.items():
        if key not in _CANDIDATE_PATCHABLE_KEYS:
            continue
        setattr(c, key, val)

    # Profile status drives the same pipeline as job_applicants; keep rows in sync so the dashboard
    # applicant tracker reflects edits from the candidate page, not only the job Applicants tab.
    if "status" in upd:
        st = str(c.status or "new").strip().lower()
        if st in STORAGE_APPLICANT_STATUSES:
            now = datetime.utcnow()
            for app in db.query(JobApplicant).filter(JobApplicant.candidate_id == c.id).all():
                app.status = st
                app.updated_at = now

    db.commit()
    db.refresh(c)
    w = None
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
    ws = workspace_best_scores(db, w, [c.id]).get(c.id) if w is not None else None
    # Use workspace-specific job ID for enrichment so job metadata is never leaked
    # across workspaces (recruiter 2 must not see recruiter 1's best-job metadata).
    jid = ws[1] if ws else ("" if w is not None else (getattr(c, "best_job_external_id", "") or "").strip())
    extra = _best_job_enrichment_map(db, {jid}).get(jid, {}) if jid else {}
    mapped = {
        "best_job_title": extra.get("title") or None,
        "best_job_department": extra.get("department") or None,
        "best_job_client_name": extra.get("client_name") or None,
        "best_job_client_company": extra.get("client_company") or None,
        "best_job_client_contact": extra.get("client_contact") or None,
        "best_job_client_email": extra.get("client_email") or None,
    }
    return _serialize_candidate_read(db, c, enrich=mapped if jid else None, ws_score=ws, recruiter_scoped=w is not None)


@router.post("/compare")
def compare_candidates(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Compare 2–6 candidates side-by-side (fast fields + best match snapshot).
    """
    raw_ids = body.get("candidate_ids") or body.get("ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=422, detail="candidate_ids must be a list of UUID strings")
    ids: list[UUID] = []
    for x in raw_ids:
        try:
            ids.append(UUID(str(x)))
        except Exception:
            raise HTTPException(status_code=422, detail=f"Invalid candidate id: {x}")
    ids = list(dict.fromkeys(ids))  # stable de-dupe
    if len(ids) < 2 or len(ids) > 6:
        raise HTTPException(status_code=422, detail="Select between 2 and 6 candidates to compare")

    w = None
    cand_q = db.query(Candidate).filter(Candidate.id.in_(ids))
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            cand_q = candidate_query_filtered_for_workspace(cand_q, w)
    cands = cand_q.all()
    by_id = {c.id: c for c in cands}
    missing = [str(i) for i in ids if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Candidates not found: {', '.join(missing)}")

    # Workspace-scoped best scores — never expose scores from another recruiter's run.
    ws_score_map = workspace_best_scores(db, w, list(by_id.keys())) if w is not None else {}

    # Derive enrichment job IDs from workspace-specific best job, not the global cache.
    job_ids: set[str] = set()
    for cid, c in by_id.items():
        ws = ws_score_map.get(cid)
        jid = ws[1] if ws else ("" if w is not None else (getattr(c, "best_job_external_id", "") or "").strip())
        if jid:
            job_ids.add(jid)
    enrich_by_job = _best_job_enrichment_map(db, job_ids)

    cols = []
    for cid in ids:
        c = by_id[cid]
        ws = ws_score_map.get(cid)
        jid = ws[1] if ws else ("" if w is not None else (getattr(c, "best_job_external_id", "") or "").strip())
        score = (ws[0] if ws[0] >= 0 else None) if ws is not None else (None if w is not None else getattr(c, "best_job_match_score", None))
        ej = enrich_by_job.get(jid, {}) if jid else {}
        cols.append(
            {
                "id": str(c.id),
                "external_id": c.external_id,
                "full_name": c.full_name,
                "title": resolve_candidate_headline(c),
                "role_label": c.role_label,
                "role_fine": c.role_fine,
                "skills": c.skills,
                "years_experience": c.years_experience,
                "highest_degree": c.highest_degree,
                "certifications": c.certifications,
                "status": c.status,
                "contact_email": c.contact_email,
                "best_job_match_score": score,
                "best_job_external_id": jid or None,
                "best_job_title": (ej.get("title") or None) if jid else None,
                "best_job_department": (ej.get("department") or None) if jid else None,
                "best_job_client_name": (ej.get("client_name") or None) if jid else None,
                "best_job_client_company": (ej.get("client_company") or None) if jid else None,
                "best_job_client_contact": (ej.get("client_contact") or None) if jid else None,
                "best_job_client_email": (ej.get("client_email") or None) if jid else None,
            }
        )

    return {"candidates": cols}


@router.get("/{candidate_uuid}", response_model=CandidateRead)
def get_candidate(
    candidate_uuid: UUID,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_candidate_self_or_recruiter(c, user)
    _ensure_recruiter_sees_candidate(db, c, user)
    w = None
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
    ws = workspace_best_scores(db, w, [c.id]).get(c.id) if w is not None else None
    jid = ws[1] if ws else (getattr(c, "best_job_external_id", "") or "").strip()
    extra = _best_job_enrichment_map(db, {jid}).get(jid, {}) if jid else {}
    mapped = {
        "best_job_title": extra.get("title") or None,
        "best_job_department": extra.get("department") or None,
        "best_job_client_name": extra.get("client_name") or None,
        "best_job_client_company": extra.get("client_company") or None,
        "best_job_client_contact": extra.get("client_contact") or None,
        "best_job_client_email": extra.get("client_email") or None,
    }
    return _serialize_candidate_read(db, c, enrich=mapped if jid else None, ws_score=ws, recruiter_scoped=w is not None)


@router.post("", response_model=CandidateRead, status_code=201)
def create_candidate(
    body: CandidateCreate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    existing = db.query(Candidate).filter(Candidate.external_id == body.external_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Candidate with this external_id already exists")
    # Attribute to the creating recruiter's workspace so this profile appears
    # in their Candidates list / dashboard immediately, without requiring a
    # subsequent job link.
    ws_id = None
    uid = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        ws_id = ensure_workspace_for_recruiter(db, user)
        uid = user.id
    cand = Candidate(
        external_id=body.external_id,
        full_name=body.full_name,
        title=body.title,
        role_label=body.role_label,
        role_fine=(body.role_fine or "unknown")[:64],
        skills=body.skills or "",
        raw_text=body.raw_text or "",
        filename=body.filename or "",
        storage_path=(body.storage_path or "").strip()[:2048],
        years_experience=body.years_experience,
        highest_degree=body.highest_degree or "",
        certifications=body.certifications or "",
        education_lines=body.education_lines or "",
        status=(body.status or "new")[:64],
        contact_email=(body.contact_email or "").strip()[:320],
        workspace_id=ws_id,
        created_by_user_id=uid,
        is_public=False,
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    name = (cand.full_name or "").strip() or "A candidate"
    log_activity(db, kind="candidate_added", message=f"{name} added to the pool", href="/candidates", workspace_id=ws_id, user_id=uid)
    return cand


@router.delete("/by-external/{external_id}", status_code=204)
def delete_candidate_by_external_id(
    external_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    c = db.query(Candidate).filter(Candidate.external_id == external_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")

    name = (c.full_name or "").strip() or "A candidate"
    caller_role = (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() if user else "recruiter"

    # --- Candidate self-deletion ---
    # Only the candidate who owns this profile may delete it (hard delete).
    # Recruiters MUST NEVER hard-delete a public/portal-linked candidate.
    if caller_role == "candidate":
        linked_cand_id = getattr(c, "user_id", None)
        if user is None or linked_cand_id != user.id:
            raise HTTPException(status_code=403, detail="You can only delete your own candidate profile")
        # Hard delete own profile — removes all rankings/applications via CASCADE.
        db.delete(c)
        db.commit()
        return Response(status_code=204)

    # --- Recruiter deletion ---
    _ensure_recruiter_sees_candidate(db, c, user)
    caller_ws = None
    if user is not None:
        caller_ws = ensure_workspace_for_recruiter(db, user)

    is_public = getattr(c, "is_public", False)
    cand_ws = getattr(c, "workspace_id", None)
    has_portal_account = getattr(c, "user_id", None) is not None

    # Extra safeguard: even if user_id was never linked on this row, check
    # whether a candidate-role account exists with the same contact email.
    # This covers the case where a recruiter uploaded the resume before the
    # candidate registered (so user_id is still NULL on the row).
    contact_email = (getattr(c, "contact_email", "") or "").strip().lower()
    if not has_portal_account and contact_email:
        email_match = db.query(User).filter(
            func.lower(User.email) == contact_email,
            User.account_role == "candidate",
        ).first()
        if email_match:
            has_portal_account = True

    # Also protect candidates who have applied to any job — they are
    # actively participating in the platform and must never be hard-deleted
    # by a recruiter (only soft-hidden per workspace).
    has_applied = db.query(JobApplicant).filter(
        JobApplicant.candidate_id == c.id
    ).first() is not None

    # Recruiters can ONLY hard-delete a private candidate that their workspace
    # exclusively owns, has no linked portal account (by user_id or email),
    # and has never applied to any job.
    # Public candidates (portal applicants) are NEVER globally deleted by recruiters.
    sole_private_owner = (
        (not is_public)
        and (not has_portal_account)
        and (not has_applied)
        and (cand_ws is not None)
        and (caller_ws is not None)
        and (cand_ws == caller_ws)
    )

    if sole_private_owner:
        db.delete(c)
        db.commit()
    else:
        # Public or portal-linked candidate: soft-hide per recruiter workspace only.
        # The global candidate row is preserved so the candidate and other
        # recruiters are never affected.
        if caller_ws is not None:
            already = db.query(RecruiterCandidateHidden).filter_by(
                workspace_id=caller_ws, candidate_id=c.id
            ).first()
            if not already:
                db.add(RecruiterCandidateHidden(workspace_id=caller_ws, candidate_id=c.id))
                db.commit()

    # Scope the notification to the calling recruiter's workspace and user only.
    caller_uid = user.id if user is not None else None
    log_activity(db, kind="info", message=f"{name} has been deleted", href="/candidates", workspace_id=caller_ws, user_id=caller_uid)
    return Response(status_code=204)
