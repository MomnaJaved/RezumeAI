"""Compute / cache job-level top-candidate insight (LLM + shortlist-aware)."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from api.config import get_settings
from api.models import Candidate, Job, JobCandidateRanking, JobShortlistedCandidate
from api.schemas import RankingExplanationOut, StoredRankingRow
from api.services.ranking_explain import build_ranking_explanation
from api.services.top_candidate_insight import (
    build_insight_facts_document,
    build_top_candidate_insight_paragraph,
)
from api.services.top_candidate_insight_llm import generate_top_candidate_insight_llm

_log = logging.getLogger("rezume.api")


def shortlisted_candidate_ids(db: Session, job_id) -> set:
    rows = db.query(JobShortlistedCandidate.candidate_id).filter(JobShortlistedCandidate.job_id == job_id).all()
    return {cid for (cid,) in rows}


def _filter_rows_for_insight(
    rows: list[tuple[JobCandidateRanking, Candidate]],
    shortlisted_ids: set,
) -> list[tuple[JobCandidateRanking, Candidate]]:
    """When the job has any shortlist rows, only include ranked candidates still on the shortlist."""
    if not shortlisted_ids:
        out = list(rows)
    else:
        out = [(jr, c) for jr, c in rows if c.id in shortlisted_ids]
    out.sort(key=lambda x: float(x[0].cross_encoder_score or 0.0), reverse=True)
    return out


def _insight_cache_key(filtered: list[tuple[JobCandidateRanking, Candidate]], max_run_at: datetime | None) -> str:
    ids = ",".join(sorted(c.external_id for _, c in filtered))
    ts = max_run_at.isoformat() if max_run_at else ""
    raw = f"{ids}|{ts}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _row_to_stored(job, jr: JobCandidateRanking, cand: Candidate) -> tuple[StoredRankingRow, Candidate]:
    expl = None
    if getattr(jr, "explanation_json", None):
        try:
            expl = RankingExplanationOut.model_validate_json(jr.explanation_json)
        except Exception:
            expl = None
    if expl is None:
        expl = RankingExplanationOut(**build_ranking_explanation(job, cand, float(jr.cross_encoder_score or 0.0)))
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
    return row, cand


def clear_job_ranking_insight_cache(db: Session, job: Job) -> None:
    job.rankings_top_insight = None
    job.rankings_top_insight_cache_key = None
    db.add(job)


def refresh_job_ranking_top_insight(db: Session, job: Job) -> str | None:
    """
    Recompute (or reuse cache) top-candidate insight for this job.
    When a shortlist exists, only ranked candidates who are still shortlisted are considered
    (so removing the prior #1 clears stale narrative on next refresh).
    """
    settings = get_settings()
    rows = (
        db.query(JobCandidateRanking, Candidate)
        .join(Candidate, JobCandidateRanking.candidate_id == Candidate.id)
        .filter(JobCandidateRanking.job_id == job.id)
        .order_by(JobCandidateRanking.rank_position)
        .all()
    )
    if not rows:
        clear_job_ranking_insight_cache(db, job)
        db.commit()
        return None

    max_run = max((jr.run_at for jr, _ in rows if getattr(jr, "run_at", None)), default=None)
    sid = shortlisted_candidate_ids(db, job.id)
    filtered = _filter_rows_for_insight(rows, sid)
    if not filtered:
        clear_job_ranking_insight_cache(db, job)
        db.commit()
        return None

    cache_key = _insight_cache_key(filtered, max_run)
    if (job.rankings_top_insight or "").strip() and (job.rankings_top_insight_cache_key or "") == cache_key:
        return job.rankings_top_insight

    pairs = [_row_to_stored(job, jr, c) for jr, c in filtered]
    peer_scope = "shortlisted candidates" if sid else "ranked candidates for this job"
    template = build_top_candidate_insight_paragraph(job, pairs, peer_scope=peer_scope)
    facts = build_insight_facts_document(job, pairs, peer_scope=peer_scope)
    llm_text = generate_top_candidate_insight_llm(settings, facts=facts, template_fallback=template)
    final = (llm_text or "").strip() or template

    job.rankings_top_insight = final
    job.rankings_top_insight_cache_key = cache_key
    db.add(job)
    try:
        db.commit()
    except Exception as e:
        _log.warning("Could not persist ranking insight cache: %s", e)
        db.rollback()
    return final
