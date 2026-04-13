"""Run SBERT shortlist + cross-encoder rerank; return list of dicts."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.models import Candidate, Job
from api.services import ml_ranking
from api.services.candidate_display import meta_from_candidate, meta_from_csv_row
from src.inference.service import match_scores_batch


def rank_for_external_job_id(
    db: Session | None,
    external_job_id: str,
    top_k: int,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Returns (job_text_or_id, list of dicts with scores plus candidate_name, candidate_title,
    candidate_role, years_experience, highest_degree, skills_summary).
    Prefers PostgreSQL Job/Candidate if present; else CSV files.
    """
    job_text: str | None = None
    use_db = db is not None

    if use_db:
        job = db.query(Job).filter(Job.external_id == str(external_job_id)).first()
        if job:
            job_text = ml_ranking.build_job_text_from_db(job)

    if not job_text:
        jobs_df = ml_ranking.get_jobs_df()
        rows = jobs_df[jobs_df["job_id"].astype(str) == str(external_job_id)]
        if rows.empty:
            raise HTTPException(status_code=404, detail=f"Job not found: {external_job_id}")
        job_text = ml_ranking.build_job_text_from_row(rows.iloc[0])

    sbert_df = ml_ranking.get_sbert_df()
    sbert_rows = sbert_df[sbert_df["job_id"].astype(str) == str(external_job_id)]
    if sbert_rows.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No SBERT rankings for job_id={external_job_id}. Run sbert_retrieval_ranker.py",
        )
    sbert_rows = sbert_rows.sort_values("rank").head(top_k)

    to_score: list[tuple[str, dict[str, Any]]] = []
    for _, row in sbert_rows.iterrows():
        cand_ext = str(row["candidate_id"])
        sim = float(row.get("cosine_similarity", 0.0))
        cand_text: Optional[str] = None
        meta: dict[str, Any] = {}

        cand: Optional[Candidate] = None
        if use_db:
            cand = db.query(Candidate).filter(Candidate.external_id == cand_ext).first()
        if cand:
            cand_text = (ml_ranking.build_cand_text_from_db(cand) or "").strip() or None
            meta = meta_from_candidate(cand, cand_ext)

        if not cand_text:
            cands_df = ml_ranking.get_cands_df()
            cr = cands_df[cands_df["candidate_id"].astype(str) == cand_ext]
            if cr.empty:
                continue
            srow = cr.iloc[0]
            cand_text = ml_ranking.build_cand_text_from_row(srow)
            if not cand:
                meta = meta_from_csv_row(srow, cand_ext)

        payload = {
            "candidate_id": cand_ext,
            "sbert_similarity": sim,
            **meta,
        }
        to_score.append((cand_text, payload))

    texts = [t for t, _ in to_score]
    scores = match_scores_batch(job_text, texts)
    results = [{**p, "cross_encoder_score": s} for s, (_, p) in zip(scores, to_score)]

    results.sort(key=lambda x: x["cross_encoder_score"], reverse=True)
    return str(external_job_id), results
