"""
Full-pool match preview helpers: same adjusted score path as persisted rankings,
with rank computed against all workspace-visible candidates (capped for latency).
"""
from __future__ import annotations

import logging
import os
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from api.models import Candidate, Job, JobCandidateSbertScore
from api.services import ml_ranking
from api.services.ranking_adjust import adjusted_match_score
from api.services.sbert_shortlist import bytes_to_vec, embed_text
from src.inference.service import match_scores_batch

_log = logging.getLogger("rezume.api")


def _cosine_vec(a: np.ndarray, b: np.ndarray) -> float:
    an = float(np.linalg.norm(a) + 1e-12)
    bn = float(np.linalg.norm(b) + 1e-12)
    return float(np.clip(np.dot(a, b) / (an * bn), -1.0, 1.0))


def job_text_embedding(job_text: str) -> np.ndarray:
    jt = (job_text or "").strip() or " "
    return embed_text(jt).astype(np.float32, copy=False)


def semantic_similarity_for_text(job_vec: np.ndarray, cand_text: str) -> float:
    """SBERT-space cosine for arbitrary text (e.g. extension preview before DB row exists)."""
    ct = (cand_text or "").strip()
    if len(ct) < 8 or job_vec.size == 0:
        return 0.0
    cv = embed_text(ct).astype(np.float32, copy=False)
    if cv.size != job_vec.size:
        return 0.0
    return _cosine_vec(job_vec, cv)


def semantic_similarity_for_db_candidate(
    db: Session,
    job: Job,
    job_vec: np.ndarray,
    cand: Candidate,
    cand_text: str,
) -> float:
    """
    Prefer persisted stage-1 cosine for (job, candidate) when present so the
    adjusted score matches rank-and-save; otherwise embedding vs job vector.
    """
    try:
        r = (
            db.query(JobCandidateSbertScore)
            .filter(
                JobCandidateSbertScore.job_id == job.id,
                JobCandidateSbertScore.candidate_id == cand.id,
            )
            .first()
        )
        if r is not None and r.cosine_similarity is not None:
            return max(0.0, min(1.0, float(r.cosine_similarity)))
    except Exception:
        pass
    b = getattr(cand, "embedding_sbert", None)
    if b and job_vec.size > 0:
        v = bytes_to_vec(b)
        if v.size == job_vec.size:
            return _cosine_vec(job_vec, v)
    return semantic_similarity_for_text(job_vec, cand_text)


def adjusted_final_for_db_candidate(
    db: Session,
    job: Job,
    job_text: str,
    job_vec: np.ndarray,
    cand: Candidate,
    cand_text: str,
    raw_cross_encoder: float,
) -> float:
    sem = semantic_similarity_for_db_candidate(db, job, job_vec, cand, cand_text)
    adj = adjusted_match_score(
        job,
        cand,
        raw_cross_encoder_score=float(raw_cross_encoder),
        sbert_similarity=sem,
    )
    return float(adj["final_score"])


def adjusted_final_for_mock(
    job: Job,
    job_vec: np.ndarray,
    cand_mock: object,
    cand_text: str,
    raw_cross_encoder: float,
) -> float:
    sem = semantic_similarity_for_text(job_vec, cand_text)
    adj = adjusted_match_score(
        job,
        cand_mock,
        raw_cross_encoder_score=float(raw_cross_encoder),
        sbert_similarity=sem,
    )
    return float(adj["final_score"])


def workspace_pool_rank(
    db: Session,
    job: Job,
    job_text: str,
    job_vec: np.ndarray,
    preview_final_01: float,
    *,
    workspace_id: UUID,
) -> tuple[int, int, bool, int]:
    """
    Rank ``preview_final_01`` among all workspace-visible candidates with enough text.

    Returns:
        ranking_position (1-based),
        total_ranked (pool size, not counting the preview profile),
        pool_capped (hit REZUME_MATCH_PREVIEW_POOL_CAP),
        pool_considered (candidates examined before text filter).
    """
    from api.services.workspace_scope import candidate_query_filtered_for_workspace

    cap = int(os.environ.get("REZUME_MATCH_PREVIEW_POOL_CAP", "400") or "400")
    cap = max(50, min(cap, 5000))
    ce_batch = int(os.environ.get("REZUME_MATCH_PREVIEW_CE_BATCH", "40") or "40")
    ce_batch = max(8, min(ce_batch, 128))

    cq = candidate_query_filtered_for_workspace(db.query(Candidate), workspace_id)
    candidates: list[Candidate] = cq.order_by(Candidate.updated_at.desc()).limit(cap).all()
    pool_capped = len(candidates) >= cap

    pairs: list[tuple[Candidate, str]] = []
    for c in candidates:
        t = (ml_ranking.build_cand_text_from_db(c) or "").strip()
        if len(t) >= 30:
            pairs.append((c, t))

    if not pairs:
        return 1, 0, pool_capped, len(candidates)

    texts = [t for _, t in pairs]
    raws: list[float] = []
    try:
        for i in range(0, len(texts), ce_batch):
            chunk = texts[i : i + ce_batch]
            raws.extend(match_scores_batch(job_text, chunk))
    except Exception as e:
        _log.warning("workspace_pool_rank: cross-encoder batch failed: %s", e)
        return 1, 0, pool_capped, len(candidates)

    if len(raws) != len(pairs):
        _log.warning(
            "workspace_pool_rank: raw count mismatch (%s vs %s)",
            len(raws),
            len(pairs),
        )
        return 1, 0, pool_capped, len(candidates)

    finals: list[float] = []
    for (c, t), raw in zip(pairs, raws):
        try:
            finals.append(
                adjusted_final_for_db_candidate(db, job, job_text, job_vec, c, t, float(raw))
            )
        except Exception as e:
            _log.debug("workspace_pool_rank row skip: %s", e)

    total = len(finals)
    if total == 0:
        return 1, 0, pool_capped, len(candidates)
    pos = sum(1 for s in finals if s > float(preview_final_01)) + 1
    return pos, total, pool_capped, len(candidates)


def job_semantic_similarity_for_save(
    job_text: str,
    cand_text: str,
) -> float:
    """Semantic term aligned with preview (embed job + candidate match string)."""
    jt = (job_text or "").strip()
    ct = (cand_text or "").strip()
    if len(jt) < 8 or len(ct) < 8:
        return 0.0
    jv = embed_text(jt).astype(np.float32, copy=False)
    return semantic_similarity_for_text(jv, ct)
