"""Explainable ranking signals (skills overlap, experience/education vs job, missing skills)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from src.matching.weak_score import (
    classify_job_skills,
    edu_score,
    exp_score,
    overlap_ratio,
    parse_skill_str,
    compute_skill_overlap,
    weak_score,
    weighted_overlap_ratio,
)

if TYPE_CHECKING:
    from api.models import Candidate, Job


def build_ranking_explanation(job: "Job", cand: "Candidate", cross_encoder_score: float, *, raw_cross_encoder_score: float | None = None) -> Dict[str, Any]:
    job_skills = parse_skill_str(str(getattr(job, "skills", None) or ""))
    cand_skills = parse_skill_str(str(getattr(cand, "skills", None) or ""))
    skills_match_ratio = float(overlap_ratio(job_skills, cand_skills)) if job_skills else 0.0
    normalized_skill_overlap = float(compute_skill_overlap(job_skills, cand_skills)) if job_skills else 0.0

    all_s, critical_s, weights = classify_job_skills(job_skills)
    total_cov = float(weighted_overlap_ratio(all_s, cand_skills, weights)) if all_s else 0.0
    critical_cov = float(overlap_ratio(critical_s, cand_skills)) if critical_s else 0.0

    missing_skills: List[str] = sorted(all_s - cand_skills)[:30]
    missing_critical: List[str] = sorted(critical_s - cand_skills)[:30]
    experience_match = float(exp_score(cand.years_experience, job.min_experience))
    education_match = float(
        edu_score(
            str(getattr(cand, "highest_degree", None) or ""),
            str(getattr(job, "education_required", None) or "any"),
        )
    )
    heuristic = float(weak_score(job_skills, cand_skills, experience_match, education_match))
    return {
        "skills_match_ratio": round(skills_match_ratio, 4),
        "normalized_skill_overlap": round(normalized_skill_overlap, 4),
        "total_skill_coverage": round(total_cov, 4),
        "critical_skill_coverage": round(critical_cov, 4),
        "experience_match": round(experience_match, 4),
        "education_match": round(education_match, 4),
        "heuristic_weak_score": round(heuristic, 4),
        "missing_skills": missing_skills,
        "missing_critical_skills": missing_critical,
        "cross_encoder_score_raw": round(float(raw_cross_encoder_score if raw_cross_encoder_score is not None else cross_encoder_score), 4),
        "cross_encoder_score": round(float(cross_encoder_score), 4),
    }
