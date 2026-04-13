"""Explainable ranking signals (skills overlap, experience/education vs job, missing skills)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from src.matching.weak_score import (
    edu_score,
    exp_score,
    overlap_ratio,
    parse_skill_str,
    weak_score,
)

if TYPE_CHECKING:
    from api.models import Candidate, Job


def build_ranking_explanation(job: "Job", cand: "Candidate", cross_encoder_score: float) -> Dict[str, Any]:
    job_skills = parse_skill_str(job.skills or "")
    cand_skills = parse_skill_str(cand.skills or "")
    skills_match_ratio = float(overlap_ratio(job_skills, cand_skills)) if job_skills else 0.0
    missing_skills: List[str] = sorted(job_skills - cand_skills)[:30]
    experience_match = float(exp_score(cand.years_experience, job.min_experience))
    education_match = float(edu_score(cand.highest_degree or "", job.education_required or "any"))
    heuristic = float(weak_score(job_skills, cand_skills, experience_match, education_match))
    return {
        "skills_match_ratio": round(skills_match_ratio, 4),
        "experience_match": round(experience_match, 4),
        "education_match": round(education_match, 4),
        "heuristic_weak_score": round(heuristic, 4),
        "missing_skills": missing_skills,
        "cross_encoder_score": round(float(cross_encoder_score), 4),
    }
