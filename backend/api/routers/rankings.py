from __future__ import annotations

import json
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_current_user_optional, require_user_if_auth_enabled
from api.models import Candidate, Job, JobApplicant, JobCandidateRanking, JobCandidateSbertScore, JobShortlistedCandidate, User
from api.schemas import JobRankingsResponse, RankingExplanationOut, StoredRankingRow
from api.services import ml_ranking
from api.services.candidate_best_job_cache import refresh_candidate_best_job_cache
from api.services.candidate_display import meta_from_candidate
from api.services.ranking_adjust import adjusted_match_score
from api.services.ranking_explain import build_ranking_explanation
from api.services.ranking_insight_sync import clear_job_ranking_insight_cache, refresh_job_ranking_top_insight, shortlisted_candidate_ids
from api.services.top_candidate_insight import build_top_candidate_insight_paragraph
from api.services.ranking_run import rank_for_external_job_id
from api.services.workspace_scope import candidate_query_filtered_for_workspace, ensure_workspace_for_recruiter
from api.services.candidate_notifications import notify_applicants_ranking_updated, notify_candidate_pipeline_status
from src.inference.service import classify_role, match_scores_batch

_log = logging.getLogger("rezume.api")

router = APIRouter(prefix="/jobs", tags=["rankings"])


def _normalize_rankings_by_match_score(rows: list[StoredRankingRow]) -> list[StoredRankingRow]:
    """
    Order by final match score (cross_encoder) descending and assign rank 1 = highest.
    Use on read so the UI always sees rank aligned with the Match % even if older DB
    rows were written before match-score ordering was fixed.
    """
    if not rows:
        return rows
    ordered = sorted(
        rows,
        key=lambda r: (
            -float(r.cross_encoder_score or 0.0),
            -float(r.sbert_similarity or 0.0),
            (r.candidate_external_id or ""),
        ),
    )
    return [r.model_copy(update={"rank_position": i}) for i, r in enumerate(ordered, start=1)]


def _require_job_in_workspace(db: Session, external_job_id: str, user: Optional[User]) -> Job:
    """
    Load job and enforce workspace ownership for recruiter accounts.
    Returns the job; raises 404 if missing or belongs to a different workspace.
    """
    job = db.query(Job).filter(Job.external_id == external_job_id).first()
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {external_job_id} not in database.",
        )
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        w = ensure_workspace_for_recruiter(db, user)
        if w is not None:
            job_ws = getattr(job, "workspace_id", None)
            if job_ws is not None and job_ws != w:
                raise HTTPException(status_code=404, detail=f"Job {external_job_id} not in database.")
    return job


def _snapshot_role(cand: Candidate, r: dict) -> str:
    role = (r.get("candidate_role") or "").strip()
    if role:
        return role
    if (cand.role_label or "").strip():
        return (cand.role_label or "").strip()
    text = (cand.raw_text or "").strip()
    if text:
        return str(classify_role(text)["label"])
    return ""


@router.post("/{external_job_id}/rank-and-save", response_model=JobRankingsResponse)
def rank_and_save(
    external_job_id: str,
    top_k: int = 50,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Runs SBERT + cross-encoder pipeline and persists results to PostgreSQL.
    Scores are stored with workspace_id for per-recruiter isolation.
    Matching ONLY adds/updates scores — it does not delete candidates.
    """
    job = _require_job_in_workspace(db, external_job_id, user)
    recruiter_ws = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        recruiter_ws = ensure_workspace_for_recruiter(db, user)

    # Always force a fresh SBERT pass when matching is explicitly triggered so
    # that candidates who applied *after* the last match run are included.
    # The stale-cache guard in rank_for_external_job_id only refreshes when the
    # cache is empty, which would leave new applicants invisible.
    try:
        from api.services.sbert_cache import refresh_sbert_for_job
        refresh_sbert_for_job(db, job, top_k=max(200, int(top_k or 50)))
    except Exception as e:
        _log.warning("SBERT refresh failed before rank_and_save for %s: %s", external_job_id, e)

    try:
        _, rows = rank_for_external_job_id(db, external_job_id, top_k)
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("rank_for_external_job_id failed: %s", e)
        raise HTTPException(status_code=500, detail="Ranking pipeline failed") from e

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No candidates scored for this job (empty shortlist or missing data).",
        )

    # Only delete rankings for this job+workspace so other recruiters' scores are untouched.
    now = datetime.utcnow()
    ranking_q = db.query(JobCandidateRanking).filter(JobCandidateRanking.job_id == job.id)
    if recruiter_ws is not None:
        ranking_q = ranking_q.filter(JobCandidateRanking.workspace_id == recruiter_ws)
    ranking_q.delete(synchronize_session=False)
    db.commit()

    run_at = now
    out_rows: list[StoredRankingRow] = []
    ranking_notify: list[tuple[Candidate, int, float]] = []

    # Apply job/candidate adjustments, then rank by the *persisted* match score. Without this
    # reorder, rank_position follows raw cross-encoder order while the UI + top insight sort by
    # adjusted scores — producing "ranked #1" text for someone stored as rank 3.
    enriched: list[tuple[float, float, dict, Candidate]] = []
    for r in rows:
        cand = db.query(Candidate).filter(Candidate.external_id == r["candidate_id"]).first()
        if not cand:
            continue
        r_work = dict(r)
        raw = float(r_work.get("cross_encoder_score_raw") or r_work["cross_encoder_score"])
        r_work["cross_encoder_score_raw"] = raw
        adj = adjusted_match_score(
            job,
            cand,
            raw_cross_encoder_score=raw,
            sbert_similarity=float(r_work.get("sbert_similarity", 0.0) or 0.0),
        )
        final = float(adj["final_score"])
        r_work["cross_encoder_score"] = final
        sbert = float(r_work.get("sbert_similarity", 0.0) or 0.0)
        enriched.append((final, sbert, r_work, cand))

    enriched.sort(key=lambda t: (-t[0], -t[1]))

    for pos, (final, _sbert, r, cand) in enumerate(enriched, start=1):
        snap_role = _snapshot_role(cand, r)
        raw = float(r.get("cross_encoder_score_raw") or r["cross_encoder_score"])
        ranking_notify.append((cand, pos, final))
        expl_raw = build_ranking_explanation(job, cand, final, raw_cross_encoder_score=raw)
        expl = RankingExplanationOut(**expl_raw)
        jr = JobCandidateRanking(
            job_id=job.id,
            candidate_id=cand.id,
            workspace_id=recruiter_ws,
            rank_position=pos,
            cross_encoder_score=final,
            sbert_similarity=r["sbert_similarity"],
            candidate_name=r.get("candidate_name") or "",
            candidate_title=r.get("candidate_title") or "",
            candidate_role=snap_role,
            years_experience=r.get("years_experience"),
            highest_degree=r.get("highest_degree") or "",
            skills_summary=r.get("skills_summary") or "",
            run_at=run_at,
            explanation_json=json.dumps(expl_raw),
        )
        db.add(jr)
        row = StoredRankingRow(
            rank_position=pos,
            cross_encoder_score=final,
            sbert_similarity=r["sbert_similarity"],
            candidate_external_id=cand.external_id,
            candidate_name=r.get("candidate_name") or "",
            candidate_title=r.get("candidate_title") or "",
            candidate_role=snap_role,
            years_experience=r.get("years_experience"),
            highest_degree=r.get("highest_degree") or "",
            skills_summary=r.get("skills_summary") or "",
            explanation=expl,
        )
        out_rows.append(row)

    db.commit()

    refresh_candidate_best_job_cache(db, [c.id for _, _, _, c in enriched])

    notify_applicants_ranking_updated(db, job, ranking_notify)

    db.refresh(job)
    insight = refresh_job_ranking_top_insight(db, job)
    return JobRankingsResponse(
        job_external_id=external_job_id,
        rankings=_normalize_rankings_by_match_score(out_rows),
        run_at=run_at,
        top_candidate_insight=insight,
    )


@router.get("/{external_job_id}/stage1-pool")
def stage1_pool(
    external_job_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Stage-1 pool for shortlisting: comes from SBERT cache.
    NEVER returns SBERT scores to the UI.
    """
    job = _require_job_in_workspace(db, external_job_id, user)
    lim = max(1, min(int(limit or 50), 500))
    rows = (
        db.query(JobCandidateSbertScore, Candidate)
        .join(Candidate, Candidate.id == JobCandidateSbertScore.candidate_id)
        .filter(JobCandidateSbertScore.job_id == job.id)
        .order_by(JobCandidateSbertScore.rank_position.asc())
        .limit(lim)
        .all()
    )
    shortlisted = {
        str(cid)
        for (cid,) in db.query(JobShortlistedCandidate.candidate_id)
        .filter(JobShortlistedCandidate.job_id == job.id)
        .all()
    }
    items = []
    for srow, cand in rows:
        meta = meta_from_candidate(cand, cand.external_id)
        items.append(
            {
                "candidate_id": cand.external_id,
                "candidate_uuid": str(cand.id),
                "candidate_name": meta.get("candidate_name", "") or (cand.full_name or ""),
                "candidate_title": meta.get("candidate_title", "") or (cand.title or ""),
                "candidate_role": meta.get("candidate_role", "") or (cand.role_label or ""),
                "years_experience": meta.get("years_experience", cand.years_experience),
                "highest_degree": meta.get("highest_degree", cand.highest_degree or ""),
                "certifications": meta.get("certifications", "") or (getattr(cand, "certifications", "") or ""),
                "skills_summary": meta.get("skills_summary", "") or (cand.skills or ""),
                # SBERT retrieval score (cosine similarity). Shown ONLY in Ranked (retrieval) list.
                "sbert_score": float(getattr(srow, "cosine_similarity", 0.0) or 0.0),
                "is_shortlisted": str(cand.id) in shortlisted,
                # Pipeline status (candidates.status — source of truth).
                "candidate_status": str(cand.status or "new").strip().lower(),
                # Pool type: True = public (portal applicant), False = private (recruiter upload).
                "is_public": bool(getattr(cand, "is_public", False)),
            }
        )
    return {"job_external_id": external_job_id, "items": items}


@router.get("/{external_job_id}/shortlist")
def get_shortlist(
    external_job_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    job = _require_job_in_workspace(db, external_job_id, user)
    rows = (
        db.query(JobShortlistedCandidate, Candidate)
        .join(Candidate, Candidate.id == JobShortlistedCandidate.candidate_id)
        .filter(JobShortlistedCandidate.job_id == job.id)
        .order_by(JobShortlistedCandidate.created_at.desc())
        .all()
    )
    items = []
    for _, cand in rows:
        meta = meta_from_candidate(cand, cand.external_id)
        items.append(
            {
                "candidate_id": cand.external_id,
                "candidate_uuid": str(cand.id),
                "candidate_name": meta.get("candidate_name", "") or (cand.full_name or ""),
                "candidate_title": meta.get("candidate_title", "") or (cand.title or ""),
                "candidate_role": meta.get("candidate_role", "") or (cand.role_label or ""),
                "years_experience": meta.get("years_experience", cand.years_experience),
                "highest_degree": meta.get("highest_degree", cand.highest_degree or ""),
                "skills_summary": meta.get("skills_summary", "") or (cand.skills or ""),
            }
        )
    return {"job_external_id": external_job_id, "items": items}


@router.post("/{external_job_id}/shortlist")
def mutate_shortlist(
    external_job_id: str,
    body: dict,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Body:
      { add: ["C001", ...], remove: ["C002", ...] } (candidate external ids)
    """
    job = _require_job_in_workspace(db, external_job_id, user)
    add = body.get("add") or []
    rem = body.get("remove") or []
    add_set = {str(x).strip() for x in add if str(x).strip()}
    rem_set = {str(x).strip() for x in rem if str(x).strip()}

    if rem_set:
        cands = db.query(Candidate).filter(Candidate.external_id.in_(list(rem_set))).all()
        ids = [c.id for c in cands]
        if ids:
            db.query(JobShortlistedCandidate).filter(
                JobShortlistedCandidate.job_id == job.id, JobShortlistedCandidate.candidate_id.in_(ids)
            ).delete(synchronize_session=False)
            # Status is NOT reset when removing from shortlist — only explicit user action changes status.
            db.commit()

    if add_set:
        existing = {
            str(cid)
            for (cid,) in db.query(JobShortlistedCandidate.candidate_id)
            .filter(JobShortlistedCandidate.job_id == job.id)
            .all()
        }
        cands = db.query(Candidate).filter(Candidate.external_id.in_(list(add_set))).all()
        promoted_shortlist: list[Candidate] = []
        for c in cands:
            if str(c.id) in existing:
                continue
            db.add(JobShortlistedCandidate(job_id=job.id, candidate_id=c.id))
            # Upsert the JobApplicant tracking row and set status to "shortlisted".
            app = (
                db.query(JobApplicant)
                .filter(JobApplicant.job_id == job.id, JobApplicant.candidate_id == c.id)
                .first()
            )
            if app:
                # Only promote — never downgrade a candidate who is already further along.
                _PROMOTE_FROM = {"new", "screened"}
                if (app.status or "new") in _PROMOTE_FROM:
                    app.status = "shortlisted"
                    app.updated_at = datetime.utcnow()
                    promoted_shortlist.append(c)
            else:
                db.add(JobApplicant(job_id=job.id, candidate_id=c.id, status="shortlisted", updated_at=datetime.utcnow()))
                promoted_shortlist.append(c)
            # Mirror on the global candidate row so the Candidates page reflects it.
            if c.status in (None, "new", "screened"):
                c.status = "shortlisted"
        db.commit()
        for c in promoted_shortlist:
            notify_candidate_pipeline_status(db, job, c, "shortlisted")

    if add_set or rem_set:
        clear_job_ranking_insight_cache(db, job)
        db.commit()

    return get_shortlist(external_job_id, db=db, user=user, _=None)


@router.post("/{external_job_id}/rank-shortlist", response_model=JobRankingsResponse)
def rank_shortlist(
    external_job_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Stage-2 ranking: cross-encoder on USER SHORTLIST only.
    Scores stored with workspace_id for per-recruiter isolation.
    """
    job = _require_job_in_workspace(db, external_job_id, user)
    recruiter_ws = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        recruiter_ws = ensure_workspace_for_recruiter(db, user)

    job_text = ml_ranking.build_job_text_from_db(job)
    if not job_text.strip():
        raise HTTPException(status_code=422, detail="Job has no description/skills text to match.")

    rows = (
        db.query(JobShortlistedCandidate, Candidate)
        .join(Candidate, Candidate.id == JobShortlistedCandidate.candidate_id)
        .filter(JobShortlistedCandidate.job_id == job.id)
        .order_by(JobShortlistedCandidate.created_at.desc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=422, detail="No shortlisted candidates yet. Shortlist candidates first.")

    # Ensure a JobApplicant tracking row exists for each shortlisted candidate.
    # Status is NOT modified here — ranking is a scoring operation, not a status decision.
    now = datetime.utcnow()
    for _, cand in rows:
        app = (
            db.query(JobApplicant)
            .filter(JobApplicant.job_id == job.id, JobApplicant.candidate_id == cand.id)
            .first()
        )
        if not app:
            db.add(JobApplicant(job_id=job.id, candidate_id=cand.id, status="new", updated_at=now))
    db.commit()

    texts = []
    payloads = []
    for _, cand in rows:
        ct = (ml_ranking.build_cand_text_from_db(cand) or "").strip()
        if not ct:
            continue
        meta = meta_from_candidate(cand, cand.external_id)
        texts.append(ct)
        payloads.append({"candidate_id": cand.external_id, **meta})

    if not payloads:
        raise HTTPException(status_code=422, detail="No candidate text could be extracted for scoring.")

    scores = match_scores_batch(job_text, texts)
    scored = [{**p, "cross_encoder_score_raw": float(s), "cross_encoder_score": float(s)} for s, p in zip(scores, payloads)]
    for r in scored:
        cand = db.query(Candidate).filter(Candidate.external_id == r["candidate_id"]).first()
        if not cand:
            continue
        adj = adjusted_match_score(job, cand, raw_cross_encoder_score=float(r["cross_encoder_score_raw"]))
        r["cross_encoder_score"] = float(adj["final_score"])
    scored.sort(key=lambda x: x["cross_encoder_score"], reverse=True)

    # Map SBERT similarity from cache (still not shown in UI)
    sbert_map = {
        str(cid): float(sim or 0.0)
        for cid, sim in db.query(JobCandidateSbertScore.candidate_id, JobCandidateSbertScore.cosine_similarity)
        .filter(JobCandidateSbertScore.job_id == job.id)
        .all()
    }

    # Only delete rankings for this job+workspace so other recruiters' scores are untouched.
    ranking_q = db.query(JobCandidateRanking).filter(JobCandidateRanking.job_id == job.id)
    if recruiter_ws is not None:
        ranking_q = ranking_q.filter(JobCandidateRanking.workspace_id == recruiter_ws)
    ranking_q.delete(synchronize_session=False)
    db.commit()

    run_at = datetime.utcnow()
    out_rows: list[StoredRankingRow] = []
    ranking_notify: list[tuple[Candidate, int, float]] = []
    for pos, r in enumerate(scored, start=1):
        cand = db.query(Candidate).filter(Candidate.external_id == r["candidate_id"]).first()
        if not cand:
            continue
        snap_role = _snapshot_role(cand, r)
        ranking_notify.append((cand, pos, float(r["cross_encoder_score"])))
        expl_raw = build_ranking_explanation(
            job,
            cand,
            float(r["cross_encoder_score"]),
            raw_cross_encoder_score=float(r.get("cross_encoder_score_raw") or r["cross_encoder_score"]),
        )
        expl = RankingExplanationOut(**expl_raw)
        db.add(
            JobCandidateRanking(
                job_id=job.id,
                candidate_id=cand.id,
                workspace_id=recruiter_ws,
                rank_position=pos,
                cross_encoder_score=float(r["cross_encoder_score"]),
                sbert_similarity=float(sbert_map.get(str(cand.id), 0.0)),
                candidate_name=r.get("candidate_name") or "",
                candidate_title=r.get("candidate_title") or "",
                candidate_role=snap_role,
                years_experience=r.get("years_experience"),
                highest_degree=r.get("highest_degree") or "",
                skills_summary=r.get("skills_summary") or "",
                run_at=run_at,
                explanation_json=json.dumps(expl_raw),
            )
        )
        row = StoredRankingRow(
            rank_position=pos,
            cross_encoder_score=float(r["cross_encoder_score"]),
            sbert_similarity=0.0,  # never shown; keep field but zero it here
            candidate_external_id=cand.external_id,
            candidate_name=r.get("candidate_name") or "",
            candidate_title=r.get("candidate_title") or "",
            candidate_role=snap_role,
            years_experience=r.get("years_experience"),
            highest_degree=r.get("highest_degree") or "",
            skills_summary=r.get("skills_summary") or "",
            explanation=expl,
        )
        out_rows.append(row)
    db.commit()

    refresh_candidate_best_job_cache(db, [cand.id for _, cand in rows])

    notify_applicants_ranking_updated(db, job, ranking_notify)

    db.refresh(job)
    insight = refresh_job_ranking_top_insight(db, job)
    return JobRankingsResponse(
        job_external_id=external_job_id,
        rankings=_normalize_rankings_by_match_score(out_rows),
        run_at=run_at,
        top_candidate_insight=insight,
    )


@router.post("/{external_job_id}/match-one")
def match_one_candidate(
    external_job_id: str,
    body: dict,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Cross-encoder match for ONE candidate vs ONE job.

    This does not require shortlisting and does not persist ranking rows; it is meant for
    the Matching page "Match" button to avoid forcing users to manage shortlists.
    """
    cand_external_id = str(body.get("candidate_id") or body.get("candidate_external_id") or "").strip()
    if not cand_external_id:
        raise HTTPException(status_code=422, detail="candidate_id is required")

    job = _require_job_in_workspace(db, external_job_id, user)
    cand = db.query(Candidate).filter(Candidate.external_id == cand_external_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job_text = ml_ranking.build_job_text_from_db(job)
    if not job_text.strip():
        raise HTTPException(status_code=422, detail="Job has no description/skills text to match.")
    ct = (ml_ranking.build_cand_text_from_db(cand) or "").strip()
    if not ct:
        raise HTTPException(status_code=422, detail="No candidate text could be extracted for scoring.")

    try:
        score = float(match_scores_batch(job_text, [ct])[0])
    except Exception as e:
        _log.exception("match_scores_batch failed: %s", e)
        raise HTTPException(status_code=503, detail="Model inference failed for match") from e

    adj = adjusted_match_score(job, cand, raw_cross_encoder_score=float(score))
    return {
        "job_external_id": external_job_id,
        "candidate_id": cand_external_id,
        "rank_position": 1,
        "cross_encoder_score": float(adj["final_score"]),
        "cross_encoder_score_raw": float(adj["raw_cross_encoder_score"]),
        "critical_skill_coverage": float(adj["critical_skill_coverage"]),
        "total_skill_coverage": float(adj["total_skill_coverage"]),
    }


@router.post("/{external_job_id}/match-batch")
def match_batch_candidates(
    external_job_id: str,
    body: dict,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Cross-encoder match for MANY candidates vs ONE job (no shortlist required).
    Returns rank positions sorted by cross-encoder score desc.
    """
    raw_ids = body.get("candidate_ids") or body.get("candidates") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(status_code=422, detail="candidate_ids must be a non-empty list")
    cand_external_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
    if not cand_external_ids:
        raise HTTPException(status_code=422, detail="candidate_ids must be a non-empty list")
    if len(cand_external_ids) > 200:
        raise HTTPException(status_code=422, detail="candidate_ids max is 200")

    job = _require_job_in_workspace(db, external_job_id, user)
    job_text = ml_ranking.build_job_text_from_db(job)
    if not job_text.strip():
        raise HTTPException(status_code=422, detail="Job has no description/skills text to match.")

    cands = db.query(Candidate).filter(Candidate.external_id.in_(cand_external_ids)).all()
    by_ext = {c.external_id: c for c in cands}

    texts: list[str] = []
    kept_ids: list[str] = []
    for ext in cand_external_ids:
        cand = by_ext.get(ext)
        if not cand:
            continue
        ct = (ml_ranking.build_cand_text_from_db(cand) or "").strip()
        if not ct:
            continue
        kept_ids.append(ext)
        texts.append(ct)

    if not kept_ids:
        raise HTTPException(status_code=422, detail="No candidate text could be extracted for scoring.")

    try:
        scores = [float(x) for x in match_scores_batch(job_text, texts)]
    except Exception as e:
        _log.exception("match_scores_batch failed: %s", e)
        raise HTTPException(status_code=503, detail="Model inference failed for match") from e

    scored = []
    for cid, s in zip(kept_ids, scores):
        cand = by_ext.get(cid)
        if not cand:
            continue
        adj = adjusted_match_score(job, cand, raw_cross_encoder_score=float(s))
        scored.append(
            {
                "candidate_id": cid,
                "cross_encoder_score": float(adj["final_score"]),
                "cross_encoder_score_raw": float(adj["raw_cross_encoder_score"]),
                "critical_skill_coverage": float(adj["critical_skill_coverage"]),
                "total_skill_coverage": float(adj["total_skill_coverage"]),
            }
        )
    scored.sort(key=lambda x: x["cross_encoder_score"], reverse=True)
    for i, row in enumerate(scored, start=1):
        row["rank_position"] = i

    top_insight = ""
    try:
        pairs = []
        for r in scored[:6]:
            ext = r["candidate_id"]
            cand = by_ext.get(ext)
            if not cand:
                continue
            meta = meta_from_candidate(cand, ext)
            row = SimpleNamespace(
                candidate_name=meta.get("candidate_name", "") or (cand.full_name or ""),
                candidate_title=meta.get("candidate_title", "") or (cand.title or ""),
                candidate_role=meta.get("candidate_role", "") or (cand.role_label or ""),
                candidate_external_id=ext,
                years_experience=meta.get("years_experience", cand.years_experience),
                highest_degree=meta.get("highest_degree", cand.highest_degree or ""),
                skills_summary=meta.get("skills_summary", "") or (cand.skills or ""),
                cross_encoder_score=float(r.get("cross_encoder_score") or 0.0),
                explanation=None,
            )
            pairs.append((row, cand))
        if pairs:
            top_insight = build_top_candidate_insight_paragraph(job, pairs, peer_scope="this ranking pool")
    except Exception:
        top_insight = ""

    return {"job_external_id": external_job_id, "items": scored, "top_candidate_insight": top_insight}


@router.post("/{external_job_id}/rank-database-candidates", response_model=JobRankingsResponse)
def rank_database_candidates(
    external_job_id: str,
    limit: int = 500,
    top_return: int = 50,
    persist: bool = False,
    prefilter: str = "sbert",
    prefilter_k: int = 200,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Scores candidates **stored in the database** (CSV sync + uploads) against one job
    using the **cross-encoder only**. Use this for **new resume uploads** that never
    appear in the offline SBERT shortlist file. `sbert_similarity` is 0.0 here.

    Set `persist=true` to replace saved ranking rows for this job+workspace.
    Candidates are filtered to those visible in the recruiter's workspace.
    """
    job = _require_job_in_workspace(db, external_job_id, user)
    recruiter_ws = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        recruiter_ws = ensure_workspace_for_recruiter(db, user)

    job_text = ml_ranking.build_job_text_from_db(job)
    if not job_text.strip():
        raise HTTPException(status_code=422, detail="Job has no description/skills text to match.")

    lim = max(1, min(limit, 5000))
    top_n = max(1, min(top_return, 500))
    pf_method = (prefilter or "none").strip().lower()
    pf_k = max(0, min(int(prefilter_k or 0), lim))

    # Filter candidates to the recruiter's workspace to prevent cross-tenant score leakage.
    cand_q = db.query(Candidate).order_by(Candidate.created_at.desc())
    if recruiter_ws is not None:
        cand_q = candidate_query_filtered_for_workspace(cand_q, recruiter_ws)
    cands = cand_q.limit(lim).all()
    if not cands:
        raise HTTPException(status_code=404, detail="No candidates in database to rank.")

    texts: list[str] = []
    payloads: list[dict] = []
    for cand in cands:
        ct = (ml_ranking.build_cand_text_from_db(cand) or "").strip()
        if not ct:
            continue
        meta = meta_from_candidate(cand, cand.external_id)
        texts.append(ct)
        payloads.append(
            {
                "candidate_id": cand.external_id,
                "sbert_similarity": 0.0,
                **meta,
            }
        )
    # Optional prefilter stage (fast shortlist) to reduce cross-encoder calls.
    if pf_method not in ("none", "tfidf", "sbert"):
        raise HTTPException(status_code=422, detail="prefilter must be one of: none, tfidf, sbert")

    if pf_method == "sbert" and pf_k > 0 and len(payloads) > pf_k:
        # Semantic shortlist using stored candidate embeddings.
        try:
            from api.services.sbert_shortlist import cosine_topk, embed_text

            # Candidate embeddings are stored on Candidate rows (bytes). We may have fewer embeddings than texts.
            cand_embs = []
            for p, cand in zip(payloads, cands):
                b = getattr(cand, "embedding_sbert", None)
                if b:
                    cand_embs.append((p["candidate_id"], b))
            if len(cand_embs) >= max(10, min(pf_k, 50)):
                q = embed_text(job_text)
                top = cosine_topk(q, cand_embs, k=pf_k)
                keep = {cid for cid, _ in top}
                # Keep only shortlisted ones (and fill sbert_similarity for reporting).
                new_texts, new_payloads = [], []
                sim_map = {cid: sim for cid, sim in top}
                for t, p in zip(texts, payloads):
                    cid = p["candidate_id"]
                    if cid in keep:
                        p = {**p, "sbert_similarity": float(sim_map.get(cid, 0.0))}
                        new_texts.append(t)
                        new_payloads.append(p)
                texts, payloads = new_texts, new_payloads
            else:
                _log.info("SBERT prefilter skipped: not enough candidate embeddings in DB.")
        except Exception as e:
            _log.warning("SBERT prefilter skipped (%s). Falling back to full pool.", e)

    if pf_method == "tfidf" and pf_k > 0 and len(texts) > pf_k:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            vec = TfidfVectorizer(
                max_features=20000,
                ngram_range=(1, 2),
                stop_words="english",
            )
            X = vec.fit_transform([job_text, *texts])
            sims = cosine_similarity(X[0], X[1:]).reshape(-1)
            top_idx = sims.argsort()[::-1][:pf_k]
            texts = [texts[i] for i in top_idx]
            payloads = [payloads[i] for i in top_idx]
        except Exception as e:
            _log.warning("TF-IDF prefilter skipped (%s). Falling back to full pool.", e)

    try:
        scores = match_scores_batch(job_text, texts)
    except Exception as e:
        _log.exception("match_scores_batch failed: %s", e)
        raise HTTPException(status_code=503, detail="Model inference failed for ranking") from e

    scored = [{**p, "cross_encoder_score_raw": float(s), "cross_encoder_score": float(s)} for s, p in zip(scores, payloads)]
    for r in scored:
        cand = db.query(Candidate).filter(Candidate.external_id == r["candidate_id"]).first()
        if not cand:
            continue
        adj = adjusted_match_score(job, cand, raw_cross_encoder_score=float(r["cross_encoder_score_raw"]), sbert_similarity=float(r.get("sbert_similarity", 0.0) or 0.0))
        r["cross_encoder_score"] = float(adj["final_score"])

    scored.sort(key=lambda x: x["cross_encoder_score"], reverse=True)
    scored = scored[:top_n]

    if not scored and cands:
        raise HTTPException(
            status_code=422,
            detail="No candidate text could be extracted for scoring.",
        )

    run_at = datetime.utcnow()
    out_rows: list[StoredRankingRow] = []
    insight_pairs: list[tuple[StoredRankingRow, Candidate]] = []
    ranking_notify: list[tuple[Candidate, int, float]] = []

    if persist:
        # Delete only this recruiter's scores for this job, preserving other tenants' data.
        ranking_q = db.query(JobCandidateRanking).filter(JobCandidateRanking.job_id == job.id)
        if recruiter_ws is not None:
            ranking_q = ranking_q.filter(JobCandidateRanking.workspace_id == recruiter_ws)
        ranking_q.delete(synchronize_session=False)
        db.commit()

    for pos, r in enumerate(scored, start=1):
        cand = db.query(Candidate).filter(Candidate.external_id == r["candidate_id"]).first()
        if not cand:
            continue
        snap_role = _snapshot_role(cand, r)
        ranking_notify.append((cand, pos, float(r["cross_encoder_score"])))
        expl_raw = build_ranking_explanation(
            job,
            cand,
            float(r["cross_encoder_score"]),
            raw_cross_encoder_score=float(r.get("cross_encoder_score_raw") or r["cross_encoder_score"]),
        )
        expl = RankingExplanationOut(**expl_raw)
        if persist:
            db.add(
                JobCandidateRanking(
                    job_id=job.id,
                    candidate_id=cand.id,
                    workspace_id=recruiter_ws,
                    rank_position=pos,
                    cross_encoder_score=float(r["cross_encoder_score"]),
                    sbert_similarity=r["sbert_similarity"],
                    candidate_name=r.get("candidate_name") or "",
                    candidate_title=r.get("candidate_title") or "",
                    candidate_role=snap_role,
                    years_experience=r.get("years_experience"),
                    highest_degree=r.get("highest_degree") or "",
                    skills_summary=r.get("skills_summary") or "",
                    run_at=run_at,
                    explanation_json=json.dumps(expl_raw),
                )
            )
        row = StoredRankingRow(
            rank_position=pos,
            cross_encoder_score=float(r["cross_encoder_score"]),
            sbert_similarity=r["sbert_similarity"],
            candidate_external_id=cand.external_id,
            candidate_name=r.get("candidate_name") or "",
            candidate_title=r.get("candidate_title") or "",
            candidate_role=snap_role,
            years_experience=r.get("years_experience"),
            highest_degree=r.get("highest_degree") or "",
            skills_summary=r.get("skills_summary") or "",
            explanation=expl,
        )
        out_rows.append(row)
        insight_pairs.append((row, cand))

    ranked_out = _normalize_rankings_by_match_score(out_rows)
    if persist:
        db.commit()
        refresh_candidate_best_job_cache(db, [c.id for c in cands if c])
        notify_applicants_ranking_updated(db, job, ranking_notify)
        db.refresh(job)
        insight = refresh_job_ranking_top_insight(db, job)
    else:
        ext_to_cand = {c.external_id: c for _, c in insight_pairs} if insight_pairs else {}
        peer_rows = [
            (r, ext_to_cand[r.candidate_external_id])
            for r in ranked_out
            if r.candidate_external_id in ext_to_cand
        ]
        peer_scope = "shortlisted candidates" if shortlisted_candidate_ids(db, job.id) else "ranked candidates for this job"
        insight = build_top_candidate_insight_paragraph(job, peer_rows, peer_scope=peer_scope) if peer_rows else None

    return JobRankingsResponse(
        job_external_id=external_job_id,
        rankings=ranked_out,
        run_at=run_at,
        top_candidate_insight=insight,
    )


@router.post("/{external_job_id}/match-candidates", response_model=JobRankingsResponse)
def match_candidates(
    external_job_id: str,
    top_k: int = 50,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Canonical match trigger: compute SBERT + cross-encoder scores, persist to
    job_candidate_rankings, and refresh each candidate's best_job_match_score.
    All frontend views should call this to trigger matching, then read from
    GET .../matches (stored data only).
    """
    return rank_and_save(external_job_id, top_k=top_k, db=db, user=user, _=None)


@router.get("/{external_job_id}/matches", response_model=JobRankingsResponse)
def get_job_matches(
    external_job_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    """
    Fetch latest persisted match scores for a job.
    Single source of truth: always reads from job_candidate_rankings.
    """
    return get_saved_rankings(external_job_id, db=db, user=user, _=None)


@router.get("/{external_job_id}/rankings", response_model=JobRankingsResponse)
def get_saved_rankings(
    external_job_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: object = Depends(require_user_if_auth_enabled),
):
    job = _require_job_in_workspace(db, external_job_id, user)
    recruiter_ws = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        recruiter_ws = ensure_workspace_for_recruiter(db, user)

    ranking_filter = [JobCandidateRanking.job_id == job.id]
    if recruiter_ws is not None:
        ranking_filter.append(JobCandidateRanking.workspace_id == recruiter_ws)

    q = (
        db.query(JobCandidateRanking, Candidate)
        .join(Candidate, JobCandidateRanking.candidate_id == Candidate.id)
        .filter(*ranking_filter)
        .order_by(JobCandidateRanking.rank_position)
    )
    rows = q.all()
    if not rows:
        raise HTTPException(status_code=404, detail="No saved rankings for this job. POST .../rank-and-save first.")

    run_at = rows[0][0].run_at
    rankings: list[StoredRankingRow] = []
    for jr, cand in rows:
        expl = None
        if getattr(jr, "explanation_json", None):
            try:
                expl = RankingExplanationOut.model_validate_json(jr.explanation_json)
            except Exception:
                expl = None
        if expl is None:
            expl = RankingExplanationOut(
                **build_ranking_explanation(job, cand, jr.cross_encoder_score)
            )
        row = StoredRankingRow(
            rank_position=jr.rank_position,
            cross_encoder_score=jr.cross_encoder_score,
            sbert_similarity=jr.sbert_similarity,
            candidate_external_id=cand.external_id,
            candidate_name=jr.candidate_name or "",
            candidate_title=jr.candidate_title or "",
            candidate_role=jr.candidate_role or "",
            years_experience=jr.years_experience,
            highest_degree=jr.highest_degree or "",
            skills_summary=jr.skills_summary or "",
            explanation=expl,
        )
        rankings.append(row)
    db.refresh(job)
    insight = refresh_job_ranking_top_insight(db, job)
    rankings = _normalize_rankings_by_match_score(rankings)
    return JobRankingsResponse(
        job_external_id=external_job_id,
        rankings=rankings,
        run_at=run_at,
        top_candidate_insight=insight,
    )
