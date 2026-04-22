"""Run SBERT shortlist + cross-encoder rerank; return list of dicts."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.models import Candidate, Job, JobCandidateSbertScore
from api.services import ml_ranking
from api.services.candidate_display import meta_from_candidate, meta_from_csv_row
from src.inference.service import match_scores_batch


def _format_empty_shortlist_detail(external_job_id: str, diag: dict | None) -> str:
    """
    Turn ``LAST_REFRESH_DIAGNOSTIC`` into a human-readable 404 message.

    The stock "run SBERT refresh" message is misleading here — we already
    auto-ran it; the real question is *why it wrote 0 rows*. Each branch below
    maps a diagnostic state to the exact user-facing cause so the recruiter
    knows whether to fix the job, re-upload resumes, or loosen thresholds.
    """
    base = f"No SBERT shortlist for job_id={external_job_id}."
    if not diag:
        return f"{base} Run SBERT refresh or sbert_retrieval_ranker.py"
    if diag.get("error"):
        return f"{base} SBERT refresh failed: {diag['error']}"
    if diag.get("job_text_empty"):
        return f"{base} The job has no title/description/skills to match against — add at least one of those and try again."
    total = int(diag.get("candidates_total", 0))
    with_emb = int(diag.get("with_embedding", 0))
    if total == 0:
        return f"{base} No candidates exist in the database yet — upload at least one resume first."
    if with_emb == 0:
        return (
            f"{base} None of the {total} candidate(s) have a usable SBERT embedding. "
            "This usually means the bulk ingestion worker didn't finish — check /ingestions status and retry failed rows."
        )
    filtered_out = int(diag.get("filtered_out", 0))
    if filtered_out > 0 and int(diag.get("passed", 0)) == 0:
        st = diag.get("sbert_threshold")
        sk = diag.get("skills_overlap_threshold")
        return (
            f"{base} {with_emb} candidate(s) had embeddings but all {filtered_out} were rejected by the match filters "
            f"(SBERT ≥ {st}, skills overlap ≥ {sk}, plus role/title check). "
            f"Either upload candidates whose skills/role match the job, or lower the thresholds via "
            f"REZUME_MATCH_SBERT_THRESHOLD / REZUME_MATCH_SKILLS_OVERLAP env vars."
        )
    if diag.get("dim_mismatch", 0) > 0:
        return (
            f"{base} Some candidate embeddings have a dimension different from the current SBERT model "
            f"({diag['dim_mismatch']} row(s)). Delete those rows or re-embed the candidates."
        )
    return f"{base} Shortlist ended up empty (diagnostic: {diag})."


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
    job_db: Job | None = None

    if use_db:
        job_db = db.query(Job).filter(Job.external_id == str(external_job_id)).first()
        if job_db:
            job_text = ml_ranking.build_job_text_from_db(job_db)

    if not job_text:
        # DB job with empty fields must not fall through to training CSVs (often absent in dev).
        if job_db is not None:
            raise HTTPException(
                status_code=422,
                detail="This job has no title, description, or skills to match against. Edit the job and add those fields, then try again.",
            )
        try:
            jobs_df = ml_ranking.get_jobs_df()
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=503,
                detail="Offline job CSV is not installed on this server. Create the job in the app with a title, description, and skills.",
            ) from e
        rows = jobs_df[jobs_df["job_id"].astype(str) == str(external_job_id)]
        if rows.empty:
            raise HTTPException(status_code=404, detail=f"Job not found: {external_job_id}")
        job_text = ml_ranking.build_job_text_from_row(rows.iloc[0])

    sbert_rows = None
    refresh_diag: dict | None = None
    if use_db and job_db is not None:
        # Always score the ENTIRE SBERT pool (up to 500 rows) so that:
        #   • Every candidate in the pool gets an accurate cross-encoder score.
        #   • The recruiter's Candidates page shows updated match scores for all.
        #   • Changing the display top-K filter never changes who scored best.
        # The display top-K is enforced by the frontend only; backend always
        # persists a JobCandidateRanking row for every scored candidate.
        q = (
            db.query(JobCandidateSbertScore, Candidate)
            .join(Candidate, Candidate.id == JobCandidateSbertScore.candidate_id)
            .filter(JobCandidateSbertScore.job_id == job_db.id)
            .order_by(JobCandidateSbertScore.rank_position.asc())
            .limit(500)
        )
        sbert_rows = q.all()
        if not sbert_rows:
            # Auto-run Stage 1 (SBERT) if cache is missing; this is fast retrieval and must happen before cross-encoder.
            try:
                from api.services.sbert_cache import LAST_REFRESH_DIAGNOSTIC, refresh_sbert_for_job

                refresh_sbert_for_job(db, job_db, top_k=max(200, int(top_k or 50)))
                sbert_rows = q.all()
                # Capture the diagnostic *after* the refresh so the 404 below
                # can tell the user whether the job has no text, no candidates
                # have embeddings, or the skills/SBERT thresholds rejected
                # every candidate. Without this the user just sees a generic
                # "run the refresh" message for a refresh that already ran.
                refresh_diag = LAST_REFRESH_DIAGNOSTIC.get(job_db.id)
            except Exception as e:
                # Best-effort; fallback to CSV if present.
                refresh_diag = {"error": str(e)[:200]}

    if not sbert_rows:
        # Fallback to legacy CSV shortlist if DB cache is missing.
        try:
            sbert_df = ml_ranking.get_sbert_df()
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=_format_empty_shortlist_detail(external_job_id, refresh_diag),
            ) from None
        sbert_rows_df = sbert_df[sbert_df["job_id"].astype(str) == str(external_job_id)]
        if sbert_rows_df.empty:
            raise HTTPException(
                status_code=404,
                detail=_format_empty_shortlist_detail(external_job_id, refresh_diag),
            )
        sbert_rows_df = sbert_rows_df.sort_values("rank").head(500)
        sbert_rows = [("csv", r) for _, r in sbert_rows_df.iterrows()]

    to_score: list[tuple[str, dict[str, Any]]] = []
    for item in sbert_rows:
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "csv":
            row = item[1]
            cand_ext = str(row["candidate_id"])
            sim = float(row.get("cosine_similarity", 0.0))
        else:
            jr, cand = item  # type: ignore[misc]
            cand_ext = str(getattr(cand, "external_id", "") or "")
            sim = float(getattr(jr, "cosine_similarity", 0.0) or 0.0)
        cand_text: Optional[str] = None
        meta: dict[str, Any] = {}

        cand_db: Optional[Candidate] = None
        if use_db:
            cand_db = db.query(Candidate).filter(Candidate.external_id == cand_ext).first()
        if cand_db:
            cand_text = (ml_ranking.build_cand_text_from_db(cand_db) or "").strip() or None
            meta = meta_from_candidate(cand_db, cand_ext)

        if not cand_text:
            try:
                cands_df = ml_ranking.get_cands_df()
            except FileNotFoundError:
                continue
            cr = cands_df[cands_df["candidate_id"].astype(str) == cand_ext]
            if cr.empty:
                continue
            srow = cr.iloc[0]
            cand_text = ml_ranking.build_cand_text_from_row(srow)
            if not cand_db:
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

    # Sort by true cross-encoder score (most accurate signal).
    # Return ALL scored candidates — the caller persists every row so that
    # the Candidates page match scores and candidate pool view are always complete.
    # Display trimming (top-K) is handled by the frontend.
    results.sort(key=lambda x: x["cross_encoder_score"], reverse=True)
    return str(external_job_id), results
