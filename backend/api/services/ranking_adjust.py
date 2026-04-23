from __future__ import annotations

import re
from typing import Any

from src.matching.weak_score import (
    classify_job_skills,
    exp_score,
    parse_skill_str,
    weighted_overlap_ratio,
)


def _clamp01(x: float) -> float:
    try:
        v = float(x or 0.0)
    except Exception:
        v = 0.0
    return max(0.0, min(1.0, v))


_SENIOR_SUPPORT_NEG = (
    ("assistant", -0.20),
    ("support", -0.15),
    ("intern", -0.25),
    ("trainee", -0.20),
    ("junior", -0.10),
)
_SENIOR_POS = (
    ("lead", 0.08),
    ("senior", 0.10),
    ("manager", 0.10),
    ("executive", 0.06),
)

_DS_ML_TITLE = re.compile(
    r"\b(data\s+scientist|data\s+science|machine\s+learning|deep\s+learning|"
    r"ml\s+engineer|nlp\s+engineer|computer\s+vision|ai\s+engineer|"
    r"research\s+scientist|quantitative\s+researcher)\b",
    re.I,
)
_UX_UI_TITLE = re.compile(
    r"\b(ui/ux|ui\s*/\s*ux|ux\s+designer|ui\s+designer|ux\s+researcher|user\s+experience|user\s+interface|"
    r"product\s+designer|interaction\s+designer|visual\s+designer|graphic\s+designer|"
    r"design\s+system)\b",
    re.I,
)


def _title_discipline_mismatch(job_title: str, cand_title: str) -> float:
    """
    Strong penalty when job and candidate titles are from incompatible families
    (e.g. Data Scientist vs UI/UX Designer). Cross-encoder text can still look vaguely similar.
    """
    jt = str(job_title or "").strip()
    ct = str(cand_title or "").strip()
    if len(jt) < 4 or len(ct) < 4:
        return 0.0
    j_ds = bool(_DS_ML_TITLE.search(jt))
    c_ds = bool(_DS_ML_TITLE.search(ct))
    j_ux = bool(_UX_UI_TITLE.search(jt))
    c_ux = bool(_UX_UI_TITLE.search(ct))
    if j_ds and c_ux and not c_ds:
        return -0.42
    if j_ux and c_ds and not j_ds:
        return -0.42
    return 0.0


def _title_role_relevance(job_title: str, cand_title: str) -> float:
    """
    Heuristic relevance for role quality. Returns [-0.3..+0.15].
    Penalizes support roles against senior job titles; boosts direct senior alignment.
    """
    jt = str(job_title or "").lower()
    ct = str(cand_title or "").lower()
    if not jt or not ct:
        return 0.0
    s = 0.0
    for tok, w in _SENIOR_SUPPORT_NEG:
        if tok in ct and any(x in jt for x, _ in _SENIOR_POS):
            s += w
    for tok, w in _SENIOR_POS:
        if tok in ct and tok in jt:
            s += w
    return max(-0.30, min(0.15, s))


def _cert_boost(job: Any, cand: Any, critical_skills: set[str]) -> float:
    """
    Small boost if candidate certifications mention critical/domain skills.
    """
    raw = str(getattr(cand, "certifications", None) or "").lower()
    if not raw.strip():
        return 0.0
    hits = 0
    for sk in list(critical_skills)[:15]:
        if sk and sk in raw:
            hits += 1
            if hits >= 2:
                break
    # Generic but helpful cert cues
    if re.search(r"hubspot|salesforce|crm", raw):
        hits += 1
    return min(0.08, 0.04 * hits)


def adjusted_match_score(job: Any, cand: Any, *, raw_cross_encoder_score: float, sbert_similarity: float | None = None) -> dict[str, Any]:
    """
    Compute a final score in [0..1] that better reflects hiring priorities:
    - base: raw cross-encoder
    - skill: weighted total coverage + critical coverage penalty
    - experience: years vs min (light)
    - role quality: title relevance (assistant/support vs exec/etc.)
    - certs: small relevance boost
    - semantic: optional SBERT similarity as mild stabilizer
    """
    base = _clamp01(raw_cross_encoder_score)

    job_skills = parse_skill_str(str(getattr(job, "skills", None) or ""))
    cand_skills = parse_skill_str(str(getattr(cand, "skills", None) or ""))
    all_s, critical_s, weights = classify_job_skills(job_skills)
    total_cov = _clamp01(weighted_overlap_ratio(all_s, cand_skills, weights)) if all_s else 0.0
    critical_cov = _clamp01(len((critical_s & cand_skills)) / len(critical_s)) if critical_s else 0.0

    # Penalize missing critical skills strongly (multiplicative).
    critical_pen = 0.55 + 0.45 * critical_cov  # 0.55..1.0

    exp_fit = _clamp01(exp_score(getattr(cand, "years_experience", None), getattr(job, "min_experience", None)))
    jt = str(getattr(job, "title", None) or "")
    ct = str(getattr(cand, "title", None) or "")
    title_rel = max(
        -0.58,
        min(0.15, _title_role_relevance(jt, ct) + _title_discipline_mismatch(jt, ct)),
    )
    cert = _cert_boost(job, cand, critical_s)
    sem = _clamp01(float(sbert_similarity or 0.0))

    # Combine: cross-encoder still primary, but corrected by critical skill penalty and structured signals.
    shaped = (0.78 * base) + (0.12 * total_cov) + (0.06 * exp_fit) + (0.04 * sem)
    shaped = _clamp01(shaped + title_rel + cert)
    final = _clamp01(shaped * critical_pen)

    return {
        "final_score": final,
        "raw_cross_encoder_score": base,
        "total_skill_coverage": total_cov,
        "critical_skill_coverage": critical_cov,
        "critical_penalty": critical_pen,
        "role_relevance_adjust": title_rel,
        "cert_boost": cert,
        "semantic_similarity": sem,
    }

