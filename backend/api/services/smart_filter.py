from __future__ import annotations

import re
from dataclasses import dataclass

from src.matching.weak_score import clean_skill_fragment


_SPLIT = re.compile(r"[,\n;/|]+")
_WORD = re.compile(r"[a-z0-9][a-z0-9+\-#.]*")


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def skills_set(raw: str) -> set[str]:
    """
    Best-effort skills parsing from comma/line separated text.
    """
    out: set[str] = set()
    stop = {"and", "or", "with", "to", "in", "of", "the", "a", "an", "for", "on", "api", "apis"}
    for chunk in _SPLIT.split(raw or ""):
        cleaned = clean_skill_fragment(chunk)
        if not cleaned:
            continue
        if cleaned in {"none", "n/a", "na", "null", "-", "—"}:
            continue
        # keep short phrases too (e.g. "rest apis") but normalize whitespace
        t = " ".join(cleaned.split())
        out.add(t)
        # also add token-level entries to make overlap robust (use cleaned chunk so
        # "figma(software" does not emit a bare "figma" token)
        for w in _WORD.findall(t):
            if w in stop:
                continue
            if len(w) < 2:
                continue
            out.add(w)
    return out


def skills_overlap_ratio(job_skills: set[str], cand_skills: set[str]) -> float:
    if not job_skills:
        return 0.0
    inter = job_skills.intersection(cand_skills)
    return float(len(inter)) / float(max(1, len(job_skills)))


def _keywords(text: str) -> set[str]:
    t = _norm(text)
    return {m.group(0) for m in _WORD.finditer(t)}


@dataclass(frozen=True)
class RoleBucket:
    key: str


def role_bucket_for_job_title(job_title: str) -> RoleBucket:
    t = _norm(job_title)
    # Minimal ATS buckets (extend safely later)
    if any(k in t for k in ["ui", "ux", "designer", "product designer", "visual", "graphics", "graphic"]):
        return RoleBucket("design")
    if any(k in t for k in ["frontend", "front-end", "react", "web"]):
        return RoleBucket("frontend")
    if any(k in t for k in ["backend", "back-end", "api", "server"]):
        return RoleBucket("backend")
    if any(k in t for k in ["fullstack", "full-stack"]):
        return RoleBucket("fullstack")
    if any(k in t for k in ["devops", "sre", "site reliability", "kubernetes"]):
        return RoleBucket("devops")
    if any(k in t for k in ["qa", "quality", "tester", "testing"]):
        return RoleBucket("qa")
    if any(k in t for k in ["data", "analyst", "bi", "warehouse"]):
        return RoleBucket("data")
    if any(k in t for k in ["finance", "account", "accounting"]):
        return RoleBucket("finance")
    if any(k in t for k in ["hr", "recruit", "talent"]):
        return RoleBucket("hr")
    if any(k in t for k in ["operations", "ops", "admin"]):
        return RoleBucket("ops")
    return RoleBucket("other")


def candidate_matches_role(job_bucket: RoleBucket, candidate_title: str, candidate_role_label: str) -> bool:
    """
    Hard reject obviously irrelevant roles (backend vs UX, etc).
    Conservative: if job bucket is 'other', allow all.
    """
    if job_bucket.key == "other":
        return True
    hay = " ".join([_norm(candidate_title), _norm(candidate_role_label)])
    if not hay.strip():
        return True

    # Allow lists per bucket (very small heuristic set)
    allow = {
        "design": ["ui", "ux", "designer", "product designer", "visual", "graphic", "graphics"],
        "frontend": ["frontend", "front-end", "react", "web", "ui"],
        "backend": ["backend", "back-end", "api", "server"],
        "fullstack": ["fullstack", "full-stack", "frontend", "backend"],
        "devops": ["devops", "sre", "kubernetes", "docker", "cloud"],
        "qa": ["qa", "tester", "testing", "quality"],
        "data": ["data", "analyst", "bi", "warehouse"],
        "finance": ["finance", "account", "accounting"],
        "hr": ["hr", "recruit", "talent"],
        "ops": ["operations", "ops", "admin"],
    }.get(job_bucket.key, [])

    reject = {
        "design": ["backend", "devops", "qa", "account", "finance", "hr"],
        "frontend": ["devops", "qa", "account", "finance", "hr"],
        "backend": ["designer", "ux", "ui designer", "graphic", "qa"],
        "devops": ["designer", "ux", "ui", "frontend", "qa"],
    }.get(job_bucket.key, [])

    if any(r in hay for r in reject):
        return False
    return any(a in hay for a in allow) if allow else True


def title_keyword_match(job_title: str, cand_title: str) -> bool:
    """
    Light title keyword check. Helps disallow unrelated jobs after SBERT retrieval.
    """
    jt = _norm(job_title)
    if not jt or jt in ("home", "unknown", "job", "role"):
        return True
    jw = _keywords(job_title)
    cw = _keywords(cand_title)
    if not jw or not cw:
        return True
    # Ignore very generic words
    stop = {"engineer", "developer", "specialist", "manager", "senior", "junior", "lead", "intern"}
    jw2 = {w for w in jw if w not in stop}
    cw2 = {w for w in cw if w not in stop}
    if not jw2 or not cw2:
        return True
    return len(jw2.intersection(cw2)) > 0


@dataclass(frozen=True)
class FilterDecision:
    passed: bool
    skills_overlap: float


def passes_filters(
    *,
    sbert_score: float,
    job_title: str,
    job_skills_raw: str,
    cand_title: str,
    cand_role_label: str,
    cand_skills_raw: str,
    sbert_threshold: float,
    skills_overlap_threshold: float,
) -> FilterDecision:
    if sbert_score < float(sbert_threshold):
        return FilterDecision(False, 0.0)

    job_sk = skills_set(job_skills_raw)
    cand_sk = skills_set(cand_skills_raw)
    ov = skills_overlap_ratio(job_sk, cand_sk) if job_sk else 0.0
    if job_sk and ov < float(skills_overlap_threshold):
        return FilterDecision(False, ov)

    bucket = role_bucket_for_job_title(job_title)
    if not candidate_matches_role(bucket, cand_title, cand_role_label):
        return FilterDecision(False, ov)

    if not title_keyword_match(job_title, cand_title):
        return FilterDecision(False, ov)

    return FilterDecision(True, ov)

