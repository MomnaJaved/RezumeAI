"""
Weak (silver) match score: skill overlap + experience + education.
Used for training the match ranker and for evaluation proxy.
"""
from __future__ import annotations

import math
import re
from typing import Iterable, Set, Dict, Iterable as _Iterable


def parse_skill_str(s: str) -> Set[str]:
    if not isinstance(s, str) or not s.strip():
        return set()
    # Normalize common separators found in job skill lists:
    # - "RabbitMQ/Kafka" → "RabbitMQ", "Kafka"
    # - "CI/CD" → "CI", "CD"
    # - "Message Queues (RabbitMQ/Kafka)" → includes "RabbitMQ", "Kafka"
    # Keep multi-word skills intact (e.g. "rest apis", "message queues").
    norm = str(s)
    norm = re.sub(r"[()]", ",", norm)  # break parenthetical groups into tokens
    norm = re.sub(r"[\\/]+", ",", norm)  # split slashes
    parts = re.split(r"[,|\n;]+", norm)
    return {normalize_skill_token(x) for x in parts if normalize_skill_token(x)}


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
    tok = re.sub(r"\s+", " ", (s or "").strip().lower())
    # Strip stray punctuation that often comes from "Kafka)" or "- AWS"
    tok = tok.strip(" .:;!?'\"`~[]{}<>|")
    return tok


def clean_skill_fragment(s: str) -> str:
    """
    Lightweight cleanup for one skill chunk before normalization.

    This exists primarily for the backend `smart_filter` stage, which parses
    job/candidate skills from pasted text and OCR where bullets/odd separators
    are common.
    """
    if not isinstance(s, str):
        return ""
    t = s.strip()
    if not t:
        return ""
    # Remove common bullet / dash prefixes and stray separators.
    t = re.sub(r"^[\s\u2022\u25CF\u25AA\u25A0\u2212\u2013\u2014\-\*\+•]+", "", t).strip()
    # Collapse internal whitespace.
    t = re.sub(r"\s+", " ", t).strip()
    # Trim trailing punctuation noise.
    t = t.strip(" \t\r\n.,;:|/\\")
    return t


# --- Skill normalization / matching -----------------------------------------
#
# Goal: avoid "false mismatches" caused by surface-form differences.
# Keep this mapping intentionally small + high-signal; it can be extended safely.
SKILL_SYNONYMS: Dict[str, Set[str]] = {
    # CI/CD
    "ci/cd pipelines": {"ci/cd", "ci", "cd", "pipelines", "cicd"},
    "ci/cd": {"ci/cd", "ci", "cd", "cicd"},
    "cicd": {"ci/cd", "ci", "cd", "cicd"},
    # Messaging
    "message queues": {"message queues", "mq", "kafka", "rabbitmq"},
    "kafka": {"kafka", "message queues"},
    "rabbitmq": {"rabbitmq", "message queues"},
    # AWS
    "aws": {"aws", "ec2", "s3", "rds", "lambda", "cloudwatch", "iam", "vpc"},
    "amazon web services": {"aws", "ec2", "s3", "rds", "lambda"},
    # Backend architecture
    "microservices": {"microservices", "distributed systems", "service architecture"},
    "distributed systems": {"distributed systems", "microservices"},
    # APIs
    "rest apis": {"rest apis", "rest", "api", "apis", "restful"},
}


def normalize_skills(skills: _Iterable[str] | Set[str]) -> Set[str]:
    """
    Normalize + expand skills into a token set.
    - Lowercase/whitespace normalize
    - Apply SKILL_SYNONYMS expansions
    - Add light variants for common punctuation forms (e.g. nodejs <-> node.js)
    """
    out: Set[str] = set()
    for raw in skills or []:
        t = normalize_skill_token(str(raw))
        if not t:
            continue
        out.add(t)
        # Dot/space variants: nodejs vs node.js, postgresql vs postgres
        if "." in t:
            out.add(t.replace(".", ""))
        if t.endswith("js"):
            out.add(t.replace(".js", "js"))
        if t == "postgresql":
            out.add("postgres")
        # Expand synonyms (both directions)
        if t in SKILL_SYNONYMS:
            out |= {normalize_skill_token(x) for x in SKILL_SYNONYMS[t]}
        else:
            for k, ex in SKILL_SYNONYMS.items():
                if t in ex:
                    out.add(normalize_skill_token(k))
                    out |= {normalize_skill_token(x) for x in ex}
    return {normalize_skill_token(x) for x in out if normalize_skill_token(x)}


def _soft_skill_match(job_skill: str, cand_skills_norm: Set[str]) -> bool:
    """
    Match strategy:
    - exact token
    - synonym-expanded token
    - partial token containment for multi-word skills (e.g. "rest api" vs "rest apis")
    """
    js = normalize_skill_token(job_skill)
    if not js:
        return False
    if js in cand_skills_norm:
        return True
    # Expand job skill and check intersection
    job_exp = normalize_skills({js})
    if job_exp & cand_skills_norm:
        return True
    # Partial containment on word boundaries (avoid very short tokens)
    if len(js) >= 4:
        for cs in cand_skills_norm:
            if len(cs) < 4:
                continue
            if js in cs or cs in js:
                return True
    return False


def compute_skill_overlap(job_skills: Set[str], cand_skills: Set[str]) -> float:
    """
    Returns a score in [0..1]:
      matched_required / total_required
    using normalized+expanded token sets and soft matching.
    """
    job_req = {normalize_skill_token(x) for x in (job_skills or set()) if normalize_skill_token(x)}
    if not job_req:
        return 0.0
    cand_norm = normalize_skills(cand_skills or set())
    matched = 0
    for js in job_req:
        if _soft_skill_match(js, cand_norm):
            matched += 1
    return clamp(matched / max(1, len(job_req)))


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


def compute_experience_score(candidate_exp: float | int | None, min_exp: float | int | None, max_exp: float | int | None) -> float:
    """
    Calibrated, step-wise experience score in [0..1].
    Intended for *final* matching (not the legacy exp_score used in old weak labels).
    """
    try:
        ce = float(candidate_exp) if candidate_exp is not None else None
    except (TypeError, ValueError):
        ce = None
    try:
        mn = float(min_exp) if min_exp is not None else None
    except (TypeError, ValueError):
        mn = None
    try:
        mx = float(max_exp) if max_exp is not None else None
    except (TypeError, ValueError):
        mx = None

    if ce is None:
        return 0.4
    if mn is None and mx is None:
        return 0.7
    if mx is None and mn is not None:
        mx = mn + 2.0  # sensible default band when only min is provided

    assert mx is not None
    if mn is None:
        mn = max(0.0, mx - 2.0)

    if mn <= ce <= mx:
        return 1.0
    if ce >= mx:
        return 0.9
    if ce >= (mn - 1.0):
        return 0.7
    return 0.4


def compute_final_score(*, semantic_similarity: float, skill_overlap: float, experience_score: float) -> float:
    """
    Additive scoring (no multiplicative penalties):
      0.5 * semantic (SBERT cosine)
    + 0.3 * skill overlap
    + 0.2 * experience
    """
    sem = clamp(float(semantic_similarity or 0.0))
    sk = clamp(float(skill_overlap or 0.0))
    ex = clamp(float(experience_score or 0.0))
    return clamp((0.5 * sem) + (0.3 * sk) + (0.2 * ex))


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
    # Legacy weak label (kept for training scripts that expect it).
    # Improve robustness by using normalized skill overlap instead of strict token overlap.
    skills_final = compute_skill_overlap(job_skills, cand_skills)
    return clamp(0.70 * skills_final + 0.20 * clamp(exp_s) + 0.10 * clamp(edu_s))
