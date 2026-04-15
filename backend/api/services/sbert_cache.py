from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from api.models import Candidate, Job, JobCandidateSbertScore
from api.services import ml_ranking

_log = logging.getLogger("rezume.api")

def refresh_sbert_for_job_id(engine, job_id, top_k: int = 200) -> int:
    """
    Background-task friendly entrypoint that creates its own DB session.
    """
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return 0
        return refresh_sbert_for_job(db, job, top_k=top_k)
    finally:
        db.close()


def ensure_candidate_embedding(db: Session, cand: Candidate) -> bool:
    """
    Ensure Candidate.embedding_sbert is populated.
    Returns True if it exists after call.
    """
    b = getattr(cand, "embedding_sbert", None)
    if b:
        return True
    try:
        from api.services.sbert_shortlist import embed_text

        text = (ml_ranking.build_cand_text_from_db(cand) or "").strip()
        if not text:
            return False
        v = embed_text(text)
        cand.embedding_sbert = v.astype("float32", copy=False).tobytes()
        db.commit()
        return True
    except Exception as e:
        _log.warning("ensure_candidate_embedding failed: %s", e)
        return False


def refresh_sbert_for_job(db: Session, job: Job, top_k: int = 200) -> int:
    """
    Recompute SBERT cosine similarities for a job vs all candidates with embeddings,
    persist top_k to JobCandidateSbertScore with rank_position.
    Returns number of stored rows.
    """
    from api.services.sbert_shortlist import bytes_to_vec, embed_text
    from api.services.smart_filter import passes_filters

    k = max(1, min(int(top_k or 200), 2000))
    job_text = (ml_ranking.build_job_text_from_db(job) or "").strip()
    if not job_text:
        return 0
    q = embed_text(job_text)

    # Dynamic thresholds (can be tuned without code changes)
    import os
    sbert_threshold = float(os.environ.get("REZUME_MATCH_SBERT_THRESHOLD", "0.05") or "0.05")
    skills_overlap_threshold = float(os.environ.get("REZUME_MATCH_SKILLS_OVERLAP", "0.20") or "0.20")

    # Compute cosine sim for all candidates with embeddings, then FILTER, then shortlist Top-K.
    qv = q.astype("float32", copy=False)
    qn = float(__import__("numpy").linalg.norm(qv) + 1e-12)

    filtered: list[tuple[str, float]] = []  # (candidate_external_id, cosine)
    by_ext: dict[str, Candidate] = {}
    for c in db.query(Candidate).all():
        if not ensure_candidate_embedding(db, c):
            continue
        b = getattr(c, "embedding_sbert", None)
        if not b:
            continue
        v = bytes_to_vec(b)
        if v.size != qv.size:
            continue
        denom = float((__import__("numpy").linalg.norm(v) + 1e-12) * qn)
        sim = float(v.dot(qv) / denom)

        # Stage-2 filtering (role + skills + threshold) BEFORE shortlist
        d = passes_filters(
            sbert_score=sim,
            job_title=(job.title or ""),
            job_skills_raw=(job.skills or ""),
            cand_title=(c.title or ""),
            cand_role_label=(c.role_label or ""),
            cand_skills_raw=(c.skills or ""),
            sbert_threshold=sbert_threshold,
            skills_overlap_threshold=skills_overlap_threshold,
        )
        if not d.passed:
            continue
        filtered.append((c.external_id, sim))
        by_ext[c.external_id] = c

    filtered.sort(key=lambda x: x[1], reverse=True)
    top = filtered[:k]

    db.query(JobCandidateSbertScore).filter(JobCandidateSbertScore.job_id == job.id).delete()
    db.commit()

    now = datetime.utcnow()
    for pos, (cand_ext, sim) in enumerate(top, start=1):
        cand = by_ext.get(cand_ext)
        if not cand:
            continue
        db.add(
            JobCandidateSbertScore(
                job_id=job.id,
                candidate_id=cand.id,
                cosine_similarity=float(sim),
                rank_position=int(pos),
                updated_at=now,
            )
        )
    db.commit()
    return len(top)


def refresh_sbert_for_all_jobs(db: Session, *, top_k: int = 200, only_active: bool = False) -> int:
    jobs_q = db.query(Job)
    if only_active:
        jobs_q = jobs_q.filter(Job.status == "active")
    jobs = jobs_q.order_by(Job.created_at.desc()).all()
    total = 0
    for j in jobs:
        try:
            total += refresh_sbert_for_job(db, j, top_k=top_k)
        except Exception as e:
            _log.warning("SBERT refresh skipped for %s: %s", getattr(j, "external_id", "?"), e)
    return total

