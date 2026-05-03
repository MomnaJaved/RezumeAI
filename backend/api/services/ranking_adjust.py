from __future__ import annotations

import logging
import os
import re
from typing import Any

from src.matching.weak_score import (
    parse_skill_str,
    compute_experience_score,
    compute_skill_overlap,
)

_log = logging.getLogger("rezume.api")


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


def _title_role_relevance(job_title: str, cand_title: str) -> float:
    """
    Heuristic relevance for role quality. Returns [-0.3..+0.15].
    Penalizes support roles against senior job titles; boosts direct senior alignment.
    """
    jt = (job_title or "").lower()
    ct = (cand_title or "").lower()
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
    raw = (getattr(cand, "certifications", None) or "").lower()
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
    Calibrated additive match score (no multiplicative penalties):

      final_score =
        0.4 * raw_cross_encoder_score
      + 0.3 * semantic_similarity   (SBERT cosine)
      + 0.2 * skill_overlap         (normalized + synonym-aware)
      + 0.1 * experience_score      (step-wise calibration)

    `raw_cross_encoder_score` remains included in the response for transparency.
    """
    raw = _clamp01(raw_cross_encoder_score)
    sem = _clamp01(float(sbert_similarity or 0.0))

    job_skills = parse_skill_str(getattr(job, "skills", None) or "")
    cand_skills = parse_skill_str(getattr(cand, "skills", None) or "")
    skill_overlap = _clamp01(compute_skill_overlap(job_skills, cand_skills))

    exp_s = _clamp01(
        compute_experience_score(
            getattr(cand, "years_experience", None),
            getattr(job, "min_experience", None),
            getattr(job, "max_experience", None) if hasattr(job, "max_experience") else None,
        )
    )

    blended = _clamp01((0.4 * raw) + (0.3 * sem) + (0.2 * skill_overlap) + (0.1 * exp_s))
    # Guardrail: never show a final Match % lower than the model's raw score.
    # This preserves "100% stays 100%" behavior when cross-encoder is perfect.
    final = max(raw, blended)

    # UI calibration: models rarely output 1.0 even for excellent matches, which makes
    # "obviously perfect" resumes look artificially low (e.g. 60–70%). Apply a monotonic
    # curve that preserves ranking order but expands the top-end.
    #
    # final := 1 - (1 - final)^gamma, with gamma > 1 boosting high scores.
    try:
        gamma = float((os.environ.get("REZUME_MATCH_CALIBRATION_GAMMA") or "").strip() or "2.0")
    except Exception:
        gamma = 2.0
    if gamma and gamma > 1.0:
        final = _clamp01(1.0 - ((1.0 - float(final)) ** gamma))

    if (os.environ.get("REZUME_MATCH_DEBUG") or "").strip().lower() in ("1", "true", "yes", "on"):
        _log.info(
            "match_debug %s",
            {
                "job": getattr(job, "external_id", None) or getattr(job, "id", None),
                "candidate": getattr(cand, "external_id", None) or getattr(cand, "id", None),
                "semantic_similarity": round(sem, 4),
                "skill_overlap": round(skill_overlap, 4),
                "experience_score": round(exp_s, 4),
                "final_score": round(final, 4),
                "raw_cross_encoder_score": round(raw, 4),
            },
        )

    return {
        "final_score": final,
        "semantic_similarity": sem,
        "skill_overlap": skill_overlap,
        "experience_score": exp_s,
        "raw_cross_encoder_score": raw,
    }

