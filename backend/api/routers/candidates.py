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
from api.models import Candidate, Client, Job, JobApplicant, JobCandidateRanking, JobCandidateSbertScore, User
from api.schemas import CandidateCreate, CandidateRead, CandidateReadWithScores, CandidateUpdate
from api.services.activity_log import log_activity
from api.services.candidate_competition_score import compute_competition_payloads_for_list
from api.services.candidate_serialization import candidate_read_dict, resolve_candidate_headline
from api.services.applicant_status_effective import STORAGE_APPLICANT_STATUSES, effective_applicant_status, sync_candidate_status_from_applicants
from api.services.workspace_scope import candidate_query_filtered_for_workspace, ensure_workspace_for_recruiter
from src.parsing.name_extractor import UNKNOWN_CANDIDATE

router = APIRouter(prefix="/candidates", tags=["candidates"])


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


def _serialize_candidate_read(db: Session, c: Candidate, *, enrich: dict[str, str | None] | None = None) -> CandidateRead:
    d = candidate_read_dict(c)
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
    q = db.query(Candidate).filter(or_(Candidate.status.is_(None), func.lower(Candidate.status) != "hired"))
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            q = candidate_query_filtered_for_workspace(q, w)
    q = q.order_by(Candidate.created_at.desc()).offset(skip).limit(limit)
    return [_serialize_candidate_read(db, c) for c in q.all()]


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
    job_ids = {(getattr(r, "best_job_external_id", "") or "").strip() for r in rows if getattr(r, "best_job_external_id", None)}
    enrich_by_job = _best_job_enrichment_map(db, job_ids)
    items: list[CandidateRead] = []
    for r in rows:
        jid = (getattr(r, "best_job_external_id", "") or "").strip()
        extra = enrich_by_job.get(jid, {}) if jid else {}
        mapped = {
            "best_job_title": extra.get("title") or None,
            "best_job_department": extra.get("department") or None,
            "best_job_client_name": extra.get("client_name") or None,
            "best_job_client_company": extra.get("client_company") or None,
            "best_job_client_contact": extra.get("client_contact") or None,
            "best_job_client_email": extra.get("client_email") or None,
        }
        items.append(_serialize_candidate_read(db, r, enrich=mapped if jid else None))
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
    cq = db.query(Candidate)
    if user is not None and getattr(user, "account_role", "") != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            cq = candidate_query_filtered_for_workspace(cq, w)
    page = cq.order_by(Candidate.created_at.desc()).offset(skip).limit(limit).all()

    # Best match across jobs is cached on Candidate to keep this endpoint fast.
    best_by_id = {c.id: float(getattr(c, "best_job_match_score", 0.0) or 0.0) for c in page}
    best_job_by_id = {c.id: (getattr(c, "best_job_external_id", "") or "").strip() or None for c in page}

    out: list[CandidateReadWithScores] = []
    for c in page:
        base = candidate_read_dict(c)
        # Keep legacy fields but avoid expensive cohort-wide computations here.
        p = 0.0
        j = 0.0
        b = float(best_by_id.get(c.id, 0.0) or 0.0)
        bj = best_job_by_id.get(c.id)
        # Keep competition_score aligned with profile strength in list views (single "Score" removed in UI).
        extra = {
            "profile_percentile_score": p,
            "avg_job_match_score": j,
            "competition_score": p,
            "best_job_match_score": b,
            "best_job_external_id": bj,
        }
        out.append(
            CandidateReadWithScores(
                **base,
                profile_percentile_score=extra["profile_percentile_score"],
                avg_job_match_score=extra["avg_job_match_score"],
                competition_score=extra["competition_score"],
                best_job_match_score=extra["best_job_match_score"],
                best_job_external_id=extra["best_job_external_id"],
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
    jid = (getattr(c, "best_job_external_id", "") or "").strip()
    extra = _best_job_enrichment_map(db, {jid}).get(jid, {}) if jid else {}
    mapped = {
        "best_job_title": extra.get("title") or None,
        "best_job_department": extra.get("department") or None,
        "best_job_client_name": extra.get("client_name") or None,
        "best_job_client_company": extra.get("client_company") or None,
        "best_job_client_contact": extra.get("client_contact") or None,
        "best_job_client_email": extra.get("client_email") or None,
    }
    return _serialize_candidate_read(db, c, enrich=mapped if jid else None)


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
    cohort = db.query(Candidate).order_by(Candidate.created_at.desc()).all()
    scores_by_id = compute_competition_payloads_for_list(db, cohort)
    base = candidate_read_dict(c)
    extra = scores_by_id.get(c.id)
    if not extra:
        extra = {
            "profile_percentile_score": 50.0,
            "avg_job_match_score": 0.0,
            "competition_score": 50.0,
        }
    best_score = float(getattr(c, "best_job_match_score", 0.0) or 0.0)
    best_job_external_id = (getattr(c, "best_job_external_id", "") or "").strip() or None
    return CandidateReadWithScores(
        **base,
        profile_percentile_score=extra["profile_percentile_score"],
        avg_job_match_score=extra["avg_job_match_score"],
        competition_score=extra["competition_score"],
        best_job_match_score=best_score,
        best_job_external_id=best_job_external_id,
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
            rq = rq.filter(Job.workspace_id == w)
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
            mq = mq.filter(Job.workspace_id == w)
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
        rnk_q = rnk_q.filter(Job.workspace_id == w)
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
    for key, val in upd.items():
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
    jid = (getattr(c, "best_job_external_id", "") or "").strip()
    extra = _best_job_enrichment_map(db, {jid}).get(jid, {}) if jid else {}
    mapped = {
        "best_job_title": extra.get("title") or None,
        "best_job_department": extra.get("department") or None,
        "best_job_client_name": extra.get("client_name") or None,
        "best_job_client_company": extra.get("client_company") or None,
        "best_job_client_contact": extra.get("client_contact") or None,
        "best_job_client_email": extra.get("client_email") or None,
    }
    return _serialize_candidate_read(db, c, enrich=mapped if jid else None)


@router.post("/compare")
def compare_candidates(body: dict = Body(...), db: Session = Depends(get_db)):
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

    cands = db.query(Candidate).filter(Candidate.id.in_(ids)).all()
    by_id = {c.id: c for c in cands}
    missing = [str(i) for i in ids if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Candidates not found: {', '.join(missing)}")

    job_ids = {(getattr(c, "best_job_external_id", "") or "").strip() for c in cands if getattr(c, "best_job_external_id", None)}
    enrich_by_job = _best_job_enrichment_map(db, job_ids)

    cols = []
    for cid in ids:
        c = by_id[cid]
        jid = (getattr(c, "best_job_external_id", "") or "").strip()
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
                "best_job_match_score": getattr(c, "best_job_match_score", None),
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
    jid = (getattr(c, "best_job_external_id", "") or "").strip()
    extra = _best_job_enrichment_map(db, {jid}).get(jid, {}) if jid else {}
    mapped = {
        "best_job_title": extra.get("title") or None,
        "best_job_department": extra.get("department") or None,
        "best_job_client_name": extra.get("client_name") or None,
        "best_job_client_company": extra.get("client_company") or None,
        "best_job_client_contact": extra.get("client_contact") or None,
        "best_job_client_email": extra.get("client_email") or None,
    }
    return _serialize_candidate_read(db, c, enrich=mapped if jid else None)


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
        skills=body.skills,
        raw_text=body.raw_text,
        filename=body.filename,
        years_experience=body.years_experience,
        highest_degree=body.highest_degree,
        certifications=body.certifications,
        education_lines=body.education_lines,
        status=(body.status or "new")[:64],
        contact_email=(body.contact_email or "").strip()[:320],
        workspace_id=ws_id,
        created_by_user_id=uid,
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    name = (cand.full_name or "").strip() or UNKNOWN_CANDIDATE
    log_activity(db, kind="candidate_added", message=f"{name} added to the pool", href="/candidates")
    return cand


@router.delete("/by-external/{external_id}", status_code=204)
def delete_candidate_by_external_id(external_id: str, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.external_id == external_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    name = (c.full_name or "").strip() or UNKNOWN_CANDIDATE
    db.delete(c)
    db.commit()
    log_activity(db, kind="info", message=f"{name} has been deleted", href="/candidates")
    return Response(status_code=204)
