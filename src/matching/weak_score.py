"""
Weak (silver) match score: skill overlap + experience + education.
Used for training the match ranker and for evaluation proxy.
"""
from __future__ import annotations

import math
import re
from typing import Iterable, Optional, Set

_LINKEDIN_QUAL_SUFFIX = re.compile(
    r"\s*\((?:software|tool|application|app|ued)\)\s*$",
    re.IGNORECASE,
)


def clean_skill_fragment(fragment: str) -> Optional[str]:
    """
    Normalize one comma-separated skill token.

    LinkedIn often labels chips as ``Figma (software)``; scrapes sometimes truncate to ``figma(software``.
    The truncated form must not be reduced to ``figma`` (false overlap with job requirements): drop it.
    A complete ``(software)`` suffix is stripped so ``Figma (software)`` overlaps ``figma``.
    """
    t = re.sub(r"\s+", " ", (fragment or "").strip().lower())
    if not t:
        return None
    last_open = t.rfind("(")
    if last_open != -1 and ")" not in t[last_open:]:
        inner = t[last_open + 1 :].strip().lower()
        if inner in {"software", "tool", "application", "app", "ued"} or (
            len(inner) <= 12 and inner.startswith("softwar")
        ):
            return None
    t = _LINKEDIN_QUAL_SUFFIX.sub("", t).strip()
    if not t:
        return None
    return t


def parse_skill_str(s: str) -> Set[str]:
    if not isinstance(s, str) or not s.strip():
        return set()
    parts = re.split(r"[,|\n;/]+", s)
    out: set[str] = set()
    for part in parts:
        tok = clean_skill_fragment(part)
        if tok:
            out.add(tok)
    return out


GENERIC_SKILLS = frozenset(
    {
        "communication",
        "communications",
        "teamwork",
        "leadership",
        "problem solving",
        "problem-solving",
        "reporting",
        "documentation",
        "ms office",
        "microsoft office",
        "excel",
        "powerpoint",
        "word",
        "presentation",
        "time management",
        "multitasking",
        "customer service",
        "interpersonal skills",
        "stakeholder management",
        "collaboration",
        "attention to detail",
    }
)


def normalize_skill_token(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def classify_job_skills(job_skills: Iterable[str]) -> tuple[set[str], set[str], dict[str, float]]:
    """
    Returns (all_skills, critical_skills, weight_by_skill).
    Critical = non-generic skills; generic skills get lower weight.
    """
    all_s = {normalize_skill_token(x) for x in job_skills if normalize_skill_token(x)}
    weight: dict[str, float] = {}
    critical: set[str] = set()
    for sk in all_s:
        if sk in GENERIC_SKILLS:
            weight[sk] = 0.25
        else:
            weight[sk] = 1.0
            critical.add(sk)
    return all_s, critical, weight


def weighted_overlap_ratio(job_skills: set[str], cand_skills: set[str], weight_by_skill: dict[str, float]) -> float:
    if not job_skills:
        return 0.0
    denom = sum(float(weight_by_skill.get(s, 1.0)) for s in job_skills)
    if denom <= 0:
        return 0.0
    num = sum(float(weight_by_skill.get(s, 1.0)) for s in job_skills if s in cand_skills)
    return num / denom


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
    # DB / JSON may surface non-strings; never call .strip on bare numbers.
    jr = str(job_req or "any").strip().lower()
    cd = str(cand_deg or "").strip().lower()
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
