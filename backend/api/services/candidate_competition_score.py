"""
Competition-style scores for the global candidate list (not tied to one job).

- Profile: percentile rank within the current candidate cohort for experience, skills count,
  education level, and certifications — then a weighted blend on a 0–100 scale.
- Job breadth: mean cross-encoder match score vs every job in the DB (each job scores all
  candidates in one or more batches), scaled to 0–100.

Final score blends profile and job breadth (equal weights when jobs exist; profile-only if not).
"""
from __future__ import annotations

import os
import re
from typing import Mapping
from uuid import UUID

from sqlalchemy.orm import Session

from api.models import Candidate, Job
from api.services import ml_ranking

# Profile mix (percentile 0–100 each → weighted sum / 100 stays 0–100).
_W_EXP = 0.32
_W_SKILLS = 0.32
_W_EDU = 0.24
_W_CERT = 0.12

# Blend when at least one job has usable text.
_W_PROFILE = 0.5
_W_JOB_BREADTH = 0.5


def _percentile_ranks_0_100(values: list[float]) -> list[float]:
    """Tie-aware percentile in [0, 100]; single item → 50."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [50.0]
    sorted_pairs = sorted(enumerate(values), key=lambda p: p[1])
    ranks: list[float] = [0.0] * n
    i = 0
    while i < n:
        j = i
        v = sorted_pairs[i][1]
        while j < n and sorted_pairs[j][1] == v:
            j += 1
        avg_rank = (i + j - 1) / 2.0
        pr = 100.0 * avg_rank / (n - 1)
        for k in range(i, j):
            idx = sorted_pairs[k][0]
            ranks[idx] = pr
        i = j
    return ranks


def _education_ordinal(highest_degree: str) -> float:
    """
    Higher = more schooling (for ranking). Used only relative to peers via percentiles.
    """
    t = re.sub(r"\s+", " ", (highest_degree or "").strip().lower())
    if not t:
        return 0.0
    if re.search(r"\b(ph\.?\s*d|doctorate|doctoral)\b", t):
        return 5.0
    if re.search(r"\b(m\.?\s*phil|mphil)\b", t):
        return 4.5
    if re.search(r"\b(m\.?\s*s|m\.?\s*sc|master|mba|m\.?\s*eng)\b", t):
        return 4.0
    if re.search(r"\b(b\.?\s*s|b\.?\s*sc|bachelor|be\b|beng|b\.?\s*a|undergraduate)\b", t):
        return 3.0
    if re.search(r"\b(intermediate|associate|diploma|a[-\s]?level)\b", t):
        return 2.0
    if re.search(r"\b(high school|matric|ssc|o[-\s]?level|ged)\b", t):
        return 1.0
    return 0.5


def _skills_count(skills: str) -> float:
    return float(
        len([x for x in re.split(r"[,;|]", skills or "") if x.strip()])
    )


def _cert_flag(certifications: str) -> float:
    return 1.0 if (certifications or "").strip() else 0.0


def _years_value(years: float | None) -> float:
    if years is None:
        return 0.0
    return max(0.0, float(years))


def compute_profile_scores_0_100(candidates: list[Candidate]) -> list[float]:
    """One profile score per candidate (same order as input), cohort-relative."""
    n = len(candidates)
    if n == 0:
        return []
    years = [_years_value(c.years_experience) for c in candidates]
    sk = [_skills_count(c.skills or "") for c in candidates]
    edu = [_education_ordinal(c.highest_degree or "") for c in candidates]
    cert = [_cert_flag(c.certifications or "") for c in candidates]

    py = _percentile_ranks_0_100(years)
    ps = _percentile_ranks_0_100(sk)
    pe = _percentile_ranks_0_100(edu)
    pc = _percentile_ranks_0_100(cert)

    out: list[float] = []
    for i in range(n):
        s = _W_EXP * py[i] + _W_SKILLS * ps[i] + _W_EDU * pe[i] + _W_CERT * pc[i]
        out.append(round(max(0.0, min(100.0, s)), 2))
    return out


def _max_jobs_for_breadth() -> int | None:
    raw = (os.environ.get("REZUME_COMPETITION_MAX_JOBS") or "").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def _batch_size_job_fit() -> int:
    try:
        return max(8, min(128, int(os.environ.get("REZUME_COMPETITION_JOB_BATCH", "48"))))
    except ValueError:
        return 48


def compute_avg_job_match_0_100(
    db: Session,
    candidates: list[Candidate],
) -> tuple[list[float], int]:
    """
    For each candidate index, mean cross-encoder score vs all (capped) jobs with non-empty text.
    Returns (scores_0_100 same order as candidates, jobs_scored_count).
    """
    n = len(candidates)
    if n == 0:
        return [], 0

    q = db.query(Job).order_by(Job.created_at.desc())
    cap = _max_jobs_for_breadth()
    if cap is not None:
        q = q.limit(cap)
    jobs = list(q.all())
    jobs = [j for j in jobs if ml_ranking.build_job_text_from_db(j).strip()]
    if not jobs:
        return [0.0] * n, 0

    cand_texts = []
    for c in candidates:
        t = (ml_ranking.build_cand_text_from_db(c) or "").strip()
        cand_texts.append(t if t else " ")

    sums = [0.0] * n
    bs = _batch_size_job_fit()

    from src.inference.service import match_scores_batch

    for job in jobs:
        jt = ml_ranking.build_job_text_from_db(job)
        for start in range(0, n, bs):
            chunk = cand_texts[start : start + bs]
            scores = match_scores_batch(jt, chunk, strip_pii_input=True, batch_size=min(bs, len(chunk)))
            for k, s in enumerate(scores):
                idx = start + k
                if idx < n:
                    sums[idx] += float(s)

    inv = 1.0 / len(jobs)
    out = [round(max(0.0, min(100.0, sums[i] * inv * 100.0)), 2) for i in range(n)]
    return out, len(jobs)


def compute_competition_payloads(
    db: Session,
    candidates: list[Candidate],
) -> Mapping[UUID, dict[str, float]]:
    """
    Map candidate.id -> {profile_percentile_score, avg_job_match_score, competition_score}.
    """
    if not candidates:
        return {}

    profile = compute_profile_scores_0_100(candidates)
    job_avgs, n_jobs = compute_avg_job_match_0_100(db, candidates)

    out: dict[UUID, dict[str, float]] = {}
    for i, c in enumerate(candidates):
        p = profile[i]
        j = job_avgs[i] if n_jobs > 0 else 50.0
        if n_jobs > 0:
            final = _W_PROFILE * p + _W_JOB_BREADTH * j
        else:
            final = p
        out[c.id] = {
            "profile_percentile_score": p,
            "avg_job_match_score": j if n_jobs > 0 else 0.0,
            "competition_score": round(max(0.0, min(100.0, final)), 2),
        }
    return out


def skip_job_breadth_for_list() -> bool:
    return os.environ.get("REZUME_COMPETITION_SKIP_JOB_FIT", "").lower() in ("1", "true", "yes")


def compute_competition_payloads_for_list(
    db: Session,
    candidates: list[Candidate],
) -> Mapping[UUID, dict[str, float]]:
    """Like compute_competition_payloads but can skip expensive CE pass via env."""
    if skip_job_breadth_for_list():
        profile = compute_profile_scores_0_100(candidates)
        return {
            c.id: {
                "profile_percentile_score": profile[i],
                "avg_job_match_score": 0.0,
                "competition_score": profile[i],
            }
            for i, c in enumerate(candidates)
        }
    return compute_competition_payloads(db, candidates)
