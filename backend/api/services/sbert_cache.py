from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from api.models import Candidate, Job, JobApplicant, JobCandidateRanking, JobCandidateSbertScore
from api.services import ml_ranking
from api.services.candidate_title_db import resolved_display_title

_log = logging.getLogger("rezume.api")

# Per-job diagnostic from the most recent ``refresh_sbert_for_job`` call.
# Keyed by Job.id (UUID) so concurrent refreshes for different jobs don't
# clobber each other. Used by the match-candidates endpoint to turn a silent
# "wrote 0 rows" into an actionable 404. Only read immediately after a call.
LAST_REFRESH_DIAGNOSTIC: dict = {}


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

    The per-job diagnostic (why the shortlist ended up empty, if it did) is
    written into the module-level ``LAST_REFRESH_DIAGNOSTIC`` cache keyed by
    job id, so the rank endpoint can surface a precise 404 reason without
    re-running the whole pass.
    """
    from api.services.sbert_shortlist import bytes_to_vec, embed_text
    from api.services.smart_filter import passes_filters

    k = max(1, min(int(top_k or 200), 2000))
    diag = {"candidates_total": 0, "with_embedding": 0, "dim_mismatch": 0, "filtered_out": 0, "passed": 0, "job_text_empty": False}
    LAST_REFRESH_DIAGNOSTIC[job.id] = diag

    job_text = (ml_ranking.build_job_text_from_db(job) or "").strip()
    if not job_text:
        diag["job_text_empty"] = True
        return 0
    q = embed_text(job_text)

    # Dynamic thresholds (can be tuned without code changes)
    import os
    sbert_threshold = float(os.environ.get("REZUME_MATCH_SBERT_THRESHOLD", "0.05") or "0.05")
    skills_overlap_threshold = float(os.environ.get("REZUME_MATCH_SKILLS_OVERLAP", "0.20") or "0.20")
    diag["sbert_threshold"] = sbert_threshold
    diag["skills_overlap_threshold"] = skills_overlap_threshold

    # Compute cosine sim for all candidates with embeddings, then FILTER, then shortlist Top-K.
    qv = q.astype("float32", copy=False)
    qn = float(__import__("numpy").linalg.norm(qv) + 1e-12)

    filtered: list[tuple[str, float]] = []  # (candidate_external_id, cosine)
    by_ext: dict[str, Candidate] = {}

    # Scope the candidate pool to the job's workspace so a recruiter never
    # sees (or inadvertently claims, via the auto-created JobApplicant row
    # below) resumes uploaded by another tenant. A job with no workspace_id
    # is legacy / pre-multi-tenant data — we fall back to the global pool in
    # that case so existing dev fixtures still rank. ``candidate_visibility_predicate``
    # is the same predicate the Candidates page and dashboard use, so the
    # shortlist can only surface people the recruiter already has access to.
    cand_q = db.query(Candidate)
    job_ws_id = getattr(job, "workspace_id", None)
    if job_ws_id is not None:
        # Self-heal cross-tenant pollution from pre-scoping refresh runs.
        # Before we added workspace scoping, ``refresh_sbert_for_job`` iterated
        # every Candidate and auto-created ``JobApplicant(status="new")`` rows
        # linking foreign candidates to this job. Those rows make the foreign
        # candidate "visible" through the job-link branch of
        # ``candidate_visibility_predicate`` even after scoping, so the
        # pollution never clears on its own.
        #
        # SAFETY: Never purge rows for portal/linked candidates (is_public=True
        # or user_id IS NOT NULL). Those rows were created by the candidate
        # choosing to apply via the portal — they are NOT pollution even if the
        # candidate's workspace_id happens to differ from the job's workspace
        # (e.g. the same resume was previously uploaded by a different recruiter
        # and the candidate later linked their account to that row, preserving
        # the original workspace_id). Purging such rows would silently erase a
        # legitimate application and make the candidate disappear from the
        # recruiter's pool immediately after applying.
        #
        # We drop only UNTOUCHED rows (status still "new") whose candidate has a
        # non-null workspace_id belonging to a *different* workspace AND who is
        # NOT a registered portal user — i.e. pure auto-created ghost rows.
        # If the recruiter progressed someone to screened/interview/etc. we
        # always preserve that deliberate decision regardless.
        stale_app_ids = [
            a_id
            for (a_id,) in db.query(JobApplicant.id)
            .join(Candidate, Candidate.id == JobApplicant.candidate_id)
            .filter(
                JobApplicant.job_id == job.id,
                JobApplicant.status == "new",
                Candidate.workspace_id.isnot(None),
                Candidate.workspace_id != job_ws_id,
                # Portal candidates opted-in voluntarily — keep their rows.
                Candidate.is_public == False,  # noqa: E712
                Candidate.user_id.is_(None),
            )
            .all()
        ]
        if stale_app_ids:
            _log.debug(
                "Purging %d stale cross-tenant applicant row(s) for job %s (ws %s)",
                len(stale_app_ids),
                job.external_id,
                job_ws_id,
            )
            db.query(JobApplicant).filter(JobApplicant.id.in_(stale_app_ids)).delete(synchronize_session=False)
            db.commit()
            diag["cross_tenant_applicants_purged"] = len(stale_app_ids)

        # Also purge stale cross-tenant ranking rows from prior refresh runs.
        # ``rank_and_save`` will wipe the rankings table for this job after we
        # return anyway, but we have to clear them *before* evaluating the
        # visibility predicate below — otherwise the ranking-link branch
        # would still mark foreign candidates as visible on this pass.
        # Same portal-safety rule: skip rows belonging to registered users.
        stale_rank_ids = [
            r_id
            for (r_id,) in db.query(JobCandidateRanking.id)
            .join(Candidate, Candidate.id == JobCandidateRanking.candidate_id)
            .filter(
                JobCandidateRanking.job_id == job.id,
                Candidate.workspace_id.isnot(None),
                Candidate.workspace_id != job_ws_id,
                Candidate.is_public == False,  # noqa: E712
                Candidate.user_id.is_(None),
            )
            .all()
        ]
        if stale_rank_ids:
            db.query(JobCandidateRanking).filter(JobCandidateRanking.id.in_(stale_rank_ids)).delete(synchronize_session=False)
            db.commit()
            diag["cross_tenant_rankings_purged"] = len(stale_rank_ids)

        from api.services.workspace_scope import candidate_visibility_predicate

        # ``candidate_visibility_predicate`` uses correlated ``exists()``
        # subqueries internally — the outer query must stay a plain
        # ``Candidate`` select with no extra joins, otherwise those
        # subqueries lose their independent Job scope.
        cand_q = cand_q.filter(candidate_visibility_predicate(job_ws_id))
    diag["workspace_scoped"] = job_ws_id is not None

    for c in cand_q.all():
        diag["candidates_total"] += 1
        if not ensure_candidate_embedding(db, c):
            continue
        b = getattr(c, "embedding_sbert", None)
        if not b:
            continue
        v = bytes_to_vec(b)
        if v.size != qv.size:
            diag["dim_mismatch"] += 1
            continue
        diag["with_embedding"] += 1
        denom = float((__import__("numpy").linalg.norm(v) + 1e-12) * qn)
        sim = float(v.dot(qv) / denom)

        # Stage-2 filtering (role + skills + threshold) BEFORE shortlist
        d = passes_filters(
            sbert_score=sim,
            job_title=(job.title or ""),
            job_skills_raw=(job.skills or ""),
            cand_title=resolved_display_title(c),
            cand_role_label=(c.role_label or ""),
            cand_skills_raw=(c.skills or ""),
            sbert_threshold=sbert_threshold,
            skills_overlap_threshold=skills_overlap_threshold,
        )
        if not d.passed:
            diag["filtered_out"] += 1
            continue
        diag["passed"] += 1
        filtered.append((c.external_id, sim))
        by_ext[c.external_id] = c

    filtered.sort(key=lambda x: x[1], reverse=True)
    top = filtered[:k]

    # Force-include job applicants who failed the SBERT/skills/role filters.
    # A candidate who explicitly applied via the portal should ALWAYS appear in
    # the recruiter's matching results — even if their resume is too sparse for
    # the semantic filters (e.g. empty skills field after NLP extraction).
    # Still record their *true* embedding cosine vs the job (not a hard-coded 0)
    # so the Matching table "SBERT" column matches what the model sees; Match %
    # comes from cross-encoder + skill/experience blending.
    top_ext_ids = {ext for ext, _ in top}
    applicant_rows = (
        db.query(JobApplicant, Candidate)
        .join(Candidate, Candidate.id == JobApplicant.candidate_id)
        .filter(JobApplicant.job_id == job.id)
        .all()
    )
    forced_applicants: list[tuple[str, float]] = []
    forced_ext_seen: set[str] = set()
    np = __import__("numpy")
    for _app, ac in applicant_rows:
        ext = str(ac.external_id or "").strip()
        # Dedupe: duplicate JobApplicant rows (same job + candidate) would otherwise
        # write multiple JobCandidateSbertScore rows and duplicate Matching table rows.
        if not ext or ext in top_ext_ids or ext in forced_ext_seen:
            continue
        forced_ext_seen.add(ext)
        ensure_candidate_embedding(db, ac)
        forced_sim = 0.0
        b_emb = getattr(ac, "embedding_sbert", None)
        if b_emb:
            try:
                vv = bytes_to_vec(b_emb)
                if vv.size == qv.size:
                    dden = float((np.linalg.norm(vv) + 1e-12) * qn)
                    if dden > 0:
                        forced_sim = float(vv.dot(qv) / dden)
            except Exception:
                forced_sim = 0.0
        forced_applicants.append((ext, forced_sim))
        by_ext[ext] = ac
    if forced_applicants:
        _log.debug(
            "Force-including %d applicant(s) excluded by SBERT/skills filters for job %s",
            len(forced_applicants),
            job.external_id,
        )
        diag["applicants_force_included"] = len(forced_applicants)

    def _dedupe_shortlist(pairs: list[tuple[str, float]]) -> list[tuple[str, float]]:
        """One row per external_id — keeps first occurrence (best SBERT rank first)."""
        seen: set[str] = set()
        out: list[tuple[str, float]] = []
        for cand_ext, sim in pairs:
            ce = str(cand_ext or "").strip()
            if not ce or ce in seen:
                continue
            seen.add(ce)
            out.append((ce, float(sim)))
        return out

    combined = _dedupe_shortlist(list(top) + forced_applicants)

    db.query(JobCandidateSbertScore).filter(JobCandidateSbertScore.job_id == job.id).delete()
    db.commit()

    now = datetime.utcnow()
    for pos, (cand_ext, sim) in enumerate(combined, start=1):
        cand = by_ext.get(cand_ext)
        if not cand:
            continue
        # Ensure applicant tracker row exists for candidates in the stage-1 pool.
        # Do not override progressed statuses; only create missing rows as NEW.
        existing_app = (
            db.query(JobApplicant)
            .filter(JobApplicant.job_id == job.id, JobApplicant.candidate_id == cand.id)
            .first()
        )
        if not existing_app:
            db.add(JobApplicant(job_id=job.id, candidate_id=cand.id, status="new", updated_at=now))
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
    return len(combined)


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

