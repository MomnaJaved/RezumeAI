from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Candidate, Job, JobCandidateRanking
from api.schemas import JobRankingsResponse, RankingExplanationOut, StoredRankingRow
from api.services import ml_ranking
from api.services.candidate_display import meta_from_candidate
from api.services.ranking_explain import build_ranking_explanation
from api.services.ranking_run import rank_for_external_job_id
from src.inference.service import classify_role, match_scores_batch

_log = logging.getLogger("rezume.api")

router = APIRouter(prefix="/jobs", tags=["rankings"])


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
):
    """
    Runs SBERT + cross-encoder pipeline and persists results to PostgreSQL.
    """
    job = db.query(Job).filter(Job.external_id == external_job_id).first()
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {external_job_id} not in database. POST /api/v1/jobs first or run sync script.",
        )

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

    db.query(JobCandidateRanking).filter(JobCandidateRanking.job_id == job.id).delete()
    db.commit()

    run_at = datetime.utcnow()
    out_rows: list[StoredRankingRow] = []

    for pos, r in enumerate(rows, start=1):
        cand = db.query(Candidate).filter(Candidate.external_id == r["candidate_id"]).first()
        if not cand:
            continue
        snap_role = _snapshot_role(cand, r)
        expl_raw = build_ranking_explanation(job, cand, r["cross_encoder_score"])
        expl = RankingExplanationOut(**expl_raw)
        jr = JobCandidateRanking(
            job_id=job.id,
            candidate_id=cand.id,
            rank_position=pos,
            cross_encoder_score=r["cross_encoder_score"],
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
        out_rows.append(
            StoredRankingRow(
                rank_position=pos,
                cross_encoder_score=r["cross_encoder_score"],
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
        )

    db.commit()

    return JobRankingsResponse(
        job_external_id=external_job_id,
        rankings=out_rows,
        run_at=run_at,
    )


@router.post("/{external_job_id}/rank-database-candidates", response_model=JobRankingsResponse)
def rank_database_candidates(
    external_job_id: str,
    limit: int = 500,
    top_return: int = 50,
    persist: bool = False,
    prefilter: str = "sbert",
    prefilter_k: int = 200,
    db: Session = Depends(get_db),
):
    """
    Scores candidates **stored in the database** (CSV sync + uploads) against one job
    using the **cross-encoder only**. Use this for **new resume uploads** that never
    appear in the offline SBERT shortlist file. `sbert_similarity` is 0.0 here.

    Set `persist=true` to replace saved ranking rows for this job (same table as
    rank-and-save).
    """
    job = db.query(Job).filter(Job.external_id == external_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_text = ml_ranking.build_job_text_from_db(job)
    if not job_text.strip():
        raise HTTPException(status_code=422, detail="Job has no description/skills text to match.")

    lim = max(1, min(limit, 5000))
    top_n = max(1, min(top_return, 500))
    pf_method = (prefilter or "none").strip().lower()
    pf_k = max(0, min(int(prefilter_k or 0), lim))
    cands = (
        db.query(Candidate)
        .order_by(Candidate.created_at.desc())
        .limit(lim)
        .all()
    )
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

    scored = [{**p, "cross_encoder_score": s} for s, p in zip(scores, payloads)]

    scored.sort(key=lambda x: x["cross_encoder_score"], reverse=True)
    scored = scored[:top_n]

    if not scored and cands:
        raise HTTPException(
            status_code=422,
            detail="No candidate text could be extracted for scoring.",
        )

    run_at = datetime.utcnow()
    out_rows: list[StoredRankingRow] = []

    if persist:
        db.query(JobCandidateRanking).filter(JobCandidateRanking.job_id == job.id).delete()
        db.commit()

    for pos, r in enumerate(scored, start=1):
        cand = db.query(Candidate).filter(Candidate.external_id == r["candidate_id"]).first()
        if not cand:
            continue
        snap_role = _snapshot_role(cand, r)
        expl_raw = build_ranking_explanation(job, cand, r["cross_encoder_score"])
        expl = RankingExplanationOut(**expl_raw)
        if persist:
            db.add(
                JobCandidateRanking(
                    job_id=job.id,
                    candidate_id=cand.id,
                    rank_position=pos,
                    cross_encoder_score=r["cross_encoder_score"],
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
        out_rows.append(
            StoredRankingRow(
                rank_position=pos,
                cross_encoder_score=r["cross_encoder_score"],
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
        )

    if persist:
        db.commit()

    return JobRankingsResponse(
        job_external_id=external_job_id,
        rankings=out_rows,
        run_at=run_at,
    )


@router.get("/{external_job_id}/rankings", response_model=JobRankingsResponse)
def get_saved_rankings(external_job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.external_id == external_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    q = (
        db.query(JobCandidateRanking, Candidate)
        .join(Candidate, JobCandidateRanking.candidate_id == Candidate.id)
        .filter(JobCandidateRanking.job_id == job.id)
        .order_by(JobCandidateRanking.rank_position)
    )
    rows = q.all()
    if not rows:
        raise HTTPException(status_code=404, detail="No saved rankings for this job. POST .../rank-and-save first.")

    run_at = rows[0][0].run_at
    rankings = []
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
        rankings.append(
            StoredRankingRow(
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
        )
    return JobRankingsResponse(
        job_external_id=external_job_id,
        rankings=rankings,
        run_at=run_at,
    )
