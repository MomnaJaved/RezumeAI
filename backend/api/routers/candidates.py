from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from fastapi import Response
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import require_user_if_auth_enabled
from api.models import Candidate, Job, JobCandidateRanking
from api.schemas import CandidateCreate, CandidateRead, CandidateReadWithScores, CandidateUpdate
from api.services.activity_log import log_activity
from api.services.candidate_competition_score import compute_competition_payloads_for_list
from src.parsing.name_extractor import UNKNOWN_CANDIDATE

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("", response_model=list[CandidateRead])
def list_candidates(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Candidate).order_by(Candidate.created_at.desc()).offset(skip).limit(limit)
    return list(q.all())


@router.get("/page")
def list_candidates_page(
    skip: int = 0,
    limit: int = Query(50, ge=1, le=100),
    q: str = "",
    status: str = "",
    role: str = "",
    sort: str = "created_desc",
    db: Session = Depends(get_db),
):
    """
    Server-side paginated candidates listing with lightweight filters.
    Returns: { total, items }.
    """
    needle = (q or "").strip()
    st = (status or "").strip().lower()
    rl = (role or "").strip().lower()
    srt = (sort or "created_desc").strip().lower()

    base = db.query(Candidate)
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
    return {"total": total, "items": [CandidateRead.model_validate(r) for r in rows]}


@router.get("/scoreboard", response_model=list[CandidateReadWithScores])
def list_candidates_scoreboard(skip: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    """
    **Candidates page only:** cohort-relative profile percentiles plus mean cross-encoder match
    vs all jobs in the DB. Expensive; do not use for generic listing.
    Set REZUME_COMPETITION_SKIP_JOB_FIT=1 to skip the job pass (profile only).
    """
    # Hard cap to prevent pathological slow requests; frontend should paginate.
    limit = max(1, min(int(limit or 50), 100))
    skip = max(0, int(skip or 0))
    page = (
        db.query(Candidate)
        .order_by(Candidate.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Best match across jobs is cached on Candidate to keep this endpoint fast.
    best_by_id = {c.id: float(getattr(c, "best_job_match_score", 0.0) or 0.0) for c in page}
    best_job_by_id = {c.id: (getattr(c, "best_job_external_id", "") or "").strip() or None for c in page}

    out: list[CandidateReadWithScores] = []
    for c in page:
        base = CandidateRead.model_validate(c)
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
                **base.model_dump(),
                profile_percentile_score=extra["profile_percentile_score"],
                avg_job_match_score=extra["avg_job_match_score"],
                competition_score=extra["competition_score"],
                best_job_match_score=extra["best_job_match_score"],
                best_job_external_id=extra["best_job_external_id"],
            )
        )
    return out


@router.get("/by-external/{external_id}", response_model=CandidateRead)
def get_candidate_by_external_id(external_id: str, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.external_id == external_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return c


@router.get("/by-external/{external_id}/file")
def download_candidate_file(
    external_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(require_user_if_auth_enabled),
):
    c = db.query(Candidate).filter(Candidate.external_id == external_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
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
def get_candidate_with_scores(candidate_uuid: UUID, db: Session = Depends(get_db)):
    """Full candidate row plus competition scores (same computation as GET /candidates/scoreboard)."""
    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    cohort = db.query(Candidate).order_by(Candidate.created_at.desc()).all()
    scores_by_id = compute_competition_payloads_for_list(db, cohort)
    base = CandidateRead.model_validate(c)
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
        **base.model_dump(),
        profile_percentile_score=extra["profile_percentile_score"],
        avg_job_match_score=extra["avg_job_match_score"],
        competition_score=extra["competition_score"],
        best_job_match_score=best_score,
        best_job_external_id=best_job_external_id,
    )


@router.get("/{candidate_uuid}/top-matches")
def candidate_top_matches(candidate_uuid: UUID, limit: int = 3, db: Session = Depends(get_db)):
    """
    Top job matches for a candidate across all jobs based on stored rankings.
    Does NOT compute any new model scores; it reads the existing matches table.
    """
    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    lim = max(1, min(int(limit or 3), 20))
    rows = (
        db.query(JobCandidateRanking, Job)
        .join(Job, Job.id == JobCandidateRanking.job_id)
        .filter(JobCandidateRanking.candidate_id == c.id)
        .order_by(JobCandidateRanking.cross_encoder_score.desc())
        .limit(lim)
        .all()
    )
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


@router.patch("/{candidate_uuid}", response_model=CandidateRead)
def patch_candidate(candidate_uuid: UUID, body: CandidateUpdate, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    upd = body.model_dump(exclude_unset=True)
    if "status" in upd and upd["status"] is not None:
        upd["status"] = str(upd["status"]).strip()[:64] or "new"
    if "role_fine" in upd and upd["role_fine"] is not None:
        upd["role_fine"] = str(upd["role_fine"]).strip()[:64] or "unknown"
    if "contact_email" in upd and upd["contact_email"] is not None:
        upd["contact_email"] = str(upd["contact_email"]).strip()[:320]
    for key, val in upd.items():
        setattr(c, key, val)
    db.commit()
    db.refresh(c)
    return c


@router.get("/{candidate_uuid}", response_model=CandidateRead)
def get_candidate(candidate_uuid: UUID, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_uuid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return c


@router.post("", response_model=CandidateRead, status_code=201)
def create_candidate(body: CandidateCreate, db: Session = Depends(get_db)):
    existing = db.query(Candidate).filter(Candidate.external_id == body.external_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Candidate with this external_id already exists")
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
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    name = (cand.full_name or "").strip() or UNKNOWN_CANDIDATE
    log_activity(db, kind="success", message=f"{name} added to the pool", href="/candidates")
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
