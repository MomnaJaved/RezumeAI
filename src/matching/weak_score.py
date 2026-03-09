"""
Weak (silver) match score: skill overlap + experience + education.
Used for training the match ranker and for evaluation proxy.
"""
from __future__ import annotations

import math
from typing import Set


def parse_skill_str(s: str) -> Set[str]:
    if not isinstance(s, str) or not s.strip():
        return set()
    return {x.strip().lower() for x in s.split(",") if x.strip()}


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def overlap_ratio(job: Set[str], cand: Set[str]) -> float:
    if not job:
        return 0.0
    return len(job & cand) / len(job)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def exp_score(cand_years: float | int | None, job_min: float | int | None) -> float:
    if job_min is None or (isinstance(job_min, float) and math.isnan(job_min)):
        return 0.5
    try:
        jm = float(job_min)
    except (TypeError, ValueError):
        return 0.5
    if cand_years is None or (isinstance(cand_years, float) and math.isnan(cand_years)):
        return 0.0
    cy = float(cand_years)
    if cy >= jm:
        return 1.0
    return clamp(cy / jm)


EDU_RANK = {"any": 0, "intermediate": 1, "bachelors": 2, "masters": 3, "phd": 4}


def edu_score(cand_deg: str, job_req: str) -> float:
    jr = (job_req or "any").strip().lower()
    cd = (cand_deg or "").strip().lower()
    if jr not in EDU_RANK or jr == "any":
        return 0.5
    if cd not in EDU_RANK:
        return 0.0
    return 1.0 if EDU_RANK[cd] >= EDU_RANK[jr] else 0.0


def weak_score(
    job_skills: Set[str],
    cand_skills: Set[str],
    exp_s: float,
    edu_s: float,
) -> float:
    skill_cov = overlap_ratio(job_skills, cand_skills)
    skill_jac = jaccard(job_skills, cand_skills)
    skills_final = 0.75 * skill_cov + 0.25 * skill_jac
    return clamp(0.70 * skills_final + 0.20 * exp_s + 0.10 * edu_s)
