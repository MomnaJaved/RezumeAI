"""Narrative 'Top Candidate Insight' for rank #1 vs peers (data-grounded template + facts for LLM)."""
from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from api.services.ranking_explain import build_ranking_explanation
from src.matching.weak_score import parse_skill_str

if TYPE_CHECKING:
    from api.models import Candidate, Job
    from api.schemas import RankingExplanationOut


@runtime_checkable
class _RankRow(Protocol):
    candidate_name: str
    candidate_title: str
    candidate_role: str
    candidate_external_id: str
    years_experience: float | int | None
    highest_degree: str
    skills_summary: str
    cross_encoder_score: float
    explanation: Any | None


def _pct01(x: float) -> int:
    v = float(x or 0.0)
    return int(round(max(0.0, min(1.0, v)) * 100))


def _match_strength(score: float) -> str:
    v = float(score or 0.0)
    if v >= 0.78:
        return "high"
    if v >= 0.62:
        return "medium"
    return "low"


def _job_title(job: Job) -> str:
    t = (getattr(job, "title", None) or "").strip()
    return t if t else "this role"


def _split_job_skill_phrases(job: Job) -> list[str]:
    raw = (getattr(job, "skills", None) or "").strip()
    if not raw:
        return []
    parts = re.split(r"[,;\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def _overlap_display_tokens(job: Job, cand: Candidate, limit: int = 5) -> list[str]:
    job_s = parse_skill_str(getattr(job, "skills", None) or "")
    cand_s = parse_skill_str(getattr(cand, "skills", None) or "")
    if not job_s or not cand_s:
        return []
    inter = job_s & cand_s
    if not inter:
        return []
    out: list[str] = []
    for phrase in _split_job_skill_phrases(job):
        low = phrase.lower()
        if low in inter:
            out.append(phrase)
        if len(out) >= limit:
            break
    return out


def _cert_snippet(cand: Candidate, max_len: int = 120) -> str:
    raw = (getattr(cand, "certifications", None) or "").strip()
    if not raw:
        return ""
    one = raw.split("|")[0].split(";")[0].strip()
    if len(one) > max_len:
        return one[: max_len - 1].rstrip() + "…"
    return one


def _expl_for_row(job: Job, cand: Candidate, row: _RankRow) -> Any:
    expl = row.explanation
    if expl is not None:
        return expl
    from api.schemas import RankingExplanationOut

    return RankingExplanationOut(**build_ranking_explanation(job, cand, float(row.cross_encoder_score or 0.0)))


def build_insight_facts_document(
    job: Job,
    ranked_pairs: list[tuple[_RankRow, Candidate]],
    *,
    peer_scope: str = "shortlisted candidates",
) -> dict[str, Any]:
    """Structured facts for the LLM (must stay consistent with template / DB)."""
    cands: list[dict[str, Any]] = []
    for row, c in ranked_pairs[:6]:
        expl = _expl_for_row(job, c, row)
        cands.append(
            {
                "external_id": row.candidate_external_id,
                "name": (row.candidate_name or "").strip() or (getattr(c, "full_name", None) or "").strip(),
                "title": (row.candidate_title or getattr(c, "title", None) or "").strip(),
                "role": (row.candidate_role or getattr(c, "role_label", None) or "").strip(),
                "cross_encoder_score_0_1": float(row.cross_encoder_score or 0.0),
                "match_percent": _pct01(float(row.cross_encoder_score or 0.0)),
                "years_experience": row.years_experience if row.years_experience is not None else getattr(c, "years_experience", None),
                "highest_degree": (row.highest_degree or getattr(c, "highest_degree", None) or "").strip(),
                "resume_skills_excerpt": ((getattr(c, "skills", None) or "")[:800]),
                "skills_summary_excerpt": (row.skills_summary or "")[:800],
                "certifications_excerpt": _cert_snippet(c, 200),
                "explanation": {
                    "skills_match_ratio": expl.skills_match_ratio,
                    "experience_match": expl.experience_match,
                    "education_match": expl.education_match,
                    "heuristic_weak_score": expl.heuristic_weak_score,
                    "missing_skills_from_job_list": list(getattr(expl, "missing_skills", None) or [])[:20],
                    "cross_encoder_score": expl.cross_encoder_score,
                },
            }
        )
    return {
        "peer_scope": peer_scope,
        "job": {
            "title": _job_title(job),
            "department": (getattr(job, "department", None) or "").strip(),
            "skills_text": ((getattr(job, "skills", None) or "")[:2000]),
            "min_experience": getattr(job, "min_experience", None),
            "education_required": (getattr(job, "education_required", None) or "").strip(),
            "description_excerpt": ((getattr(job, "description", None) or "")[:2500]),
        },
        "candidates_ranked_for_insight": cands,
    }


def build_top_candidate_insight_paragraph(
    job: Job,
    ranked_pairs: list[tuple[_RankRow, Candidate]],
    *,
    peer_scope: str = "shortlisted candidates",
) -> str:
    """
    Executive-style paragraph: rank #1 rationale, evidence from explanations + résumé fields,
    optional contrast vs #2. Uses only job/candidate/explanation data (no invented skills).
    """
    if not ranked_pairs:
        return ""

    row1, c1 = ranked_pairs[0]
    expl1 = _expl_for_row(job, c1, row1)
    name1 = (row1.candidate_name or "").strip() or (getattr(c1, "full_name", None) or "").strip() or row1.candidate_external_id
    jt = _job_title(job)
    s1 = _match_strength(float(row1.cross_encoder_score or 0.0))
    pct1 = _pct01(float(row1.cross_encoder_score or 0.0))
    cov1 = int(round(float(expl1.skills_match_ratio or 0.0) * 100))
    exp1 = float(expl1.experience_match or 0.0)
    edu1 = float(expl1.education_match or 0.0)
    miss1 = list(getattr(expl1, "missing_skills", None) or [])

    overlap = _overlap_display_tokens(job, c1, limit=6)
    title1 = (row1.candidate_title or getattr(c1, "title", None) or "").strip()
    role1 = (row1.candidate_role or getattr(c1, "role_label", None) or "").strip()
    y1 = row1.years_experience
    if y1 is not None and isinstance(y1, float) and math.isnan(y1):
        y1 = None
    if y1 is None:
        y1 = getattr(c1, "years_experience", None)
    deg1 = (row1.highest_degree or getattr(c1, "highest_degree", None) or "").strip()
    cert1 = _cert_snippet(c1)

    parts: list[str] = []

    pool_label = "this shortlist" if "shortlist" in peer_scope.lower() else "this ranking pool"
    parts.append(
        f"{name1} is ranked #1 for {jt} because their overall match score is highest among {peer_scope} "
        f"({pct1}%), with a {s1} strength rating from the ranking model, supported by structured signals on skills coverage "
        f"({cov1}% of the job’s listed requirement tags found in their résumé skills), experience fit versus the role minimum "
        f"({int(round(exp1 * 100))}%), and education alignment ({int(round(edu1 * 100))}%)."
    )

    if overlap:
        parts.append(
            f"Concrete alignment shows up in overlapping requirement areas such as {', '.join(overlap)}, drawn directly from the job’s stated skills and their résumé."
        )
    elif _split_job_skill_phrases(job):
        parts.append(
            "Keyword-level tag overlap is not dominant in the parsed skills lists; the top rank is driven mainly by the full job description versus full résumé scoring, where this profile still separates from peers."
        )

    if title1 or role1:
        headline = " / ".join(x for x in [title1, role1] if x)
        parts.append(f"Their headline profile ({headline}) reinforces domain relevance for this opening.")

    if y1 is not None:
        try:
            yy = float(y1)
        except (TypeError, ValueError):
            yy = None
        if yy is not None and not (isinstance(yy, float) and math.isnan(yy)):
            jmin = getattr(job, "min_experience", None)
            try:
                jm = float(jmin) if jmin is not None and str(jmin).strip() != "" else None
            except (TypeError, ValueError):
                jm = None
            if jm is not None and yy + 1e-6 >= jm:
                parts.append(
                    f"They report about {yy:g} years of experience, meeting or exceeding the role’s stated minimum of {jm:g} years, which supports depth expectations for delivery."
                )
            else:
                parts.append(f"They report about {yy:g} years of experience in the structured profile fields used for screening.")

    if deg1:
        parts.append(f"Education signals include {deg1.replace('_', ' ')} as the recorded highest degree.")

    if cert1:
        parts.append(f"Certifications/credentials on file include: {cert1}")

    if len(ranked_pairs) >= 2:
        row2, c2 = ranked_pairs[1]
        expl2 = _expl_for_row(job, c2, row2)
        name2 = (row2.candidate_name or "").strip() or (getattr(c2, "full_name", None) or "").strip() or row2.candidate_external_id
        pct2 = _pct01(float(row2.cross_encoder_score or 0.0))
        cov2 = int(round(float(expl2.skills_match_ratio or 0.0) * 100))
        miss2 = list(getattr(expl2, "missing_skills", None) or [])
        parts.append(
            f"Compared with {name2} at rank #2 (match score {pct2}%, tagged skills coverage {cov2}%), {name1} leads on the model score gap and shows "
            f"fewer uncovered requirement tags in the parsed job-versus-résumé view ({len(miss1)} missing vs {len(miss2)} for #2), "
            f"which is consistent with placing them ahead for this requisition."
        )

    parts.append(
        f"Overall, {name1} combines the strongest automated match score with the most favorable structured overlap and experience/education signals in {pool_label}, "
        f"so they are positioned as the highest-impact choice for advancing {jt}."
    )

    return " ".join(parts)
