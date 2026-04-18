from __future__ import annotations

from types import SimpleNamespace

from api.schemas import RankingExplanationOut, StoredRankingRow
from api.services.top_candidate_insight import build_top_candidate_insight_paragraph


def _row(
    pos: int,
    name: str,
    title: str,
    role: str,
    ext: str,
    ce: float,
    y: float | None,
    deg: str,
    expl: RankingExplanationOut,
) -> StoredRankingRow:
    return StoredRankingRow(
        rank_position=pos,
        cross_encoder_score=ce,
        sbert_similarity=0.5,
        candidate_external_id=ext,
        candidate_name=name,
        candidate_title=title,
        candidate_role=role,
        years_experience=y,
        highest_degree=deg,
        skills_summary="",
        explanation=expl,
    )


def test_insight_names_rank_one_and_overlap():
    job = SimpleNamespace(
        title="Senior Frontend Engineer",
        skills="React, TypeScript, REST APIs",
        min_experience=5.0,
        education_required="bachelors",
    )
    c1 = SimpleNamespace(
        full_name="",
        external_id="E1",
        skills="react, typescript, graphql",
        years_experience=10.0,
        highest_degree="master",
        certifications="AWS Certified Developer",
    )
    expl1 = RankingExplanationOut(
        skills_match_ratio=0.85,
        experience_match=1.0,
        education_match=1.0,
        heuristic_weak_score=0.15,
        missing_skills=["docker"],
        cross_encoder_score=0.91,
    )
    row1 = _row(1, "Alex Kim", "Staff Engineer", "frontend", "E1", 0.91, 10.0, "master", expl1)
    text = build_top_candidate_insight_paragraph(job, [(row1, c1)])
    low = text.lower()
    assert "alex kim" in low
    assert "ranked #1" in low
    assert "react" in low or "typescript" in low


def test_insight_contrasts_second_candidate():
    job = SimpleNamespace(
        title="Backend Developer",
        skills="Python, PostgreSQL",
        min_experience=3.0,
        education_required="any",
    )
    c1 = SimpleNamespace(
        full_name="A",
        external_id="A1",
        skills="Python, PostgreSQL, Django",
        years_experience=6.0,
        highest_degree="bachelor",
        certifications="",
    )
    c2 = SimpleNamespace(
        full_name="B",
        external_id="B1",
        skills="Python",
        years_experience=2.0,
        highest_degree="bachelor",
        certifications="",
    )
    expl1 = RankingExplanationOut(
        skills_match_ratio=1.0,
        experience_match=1.0,
        education_match=0.5,
        heuristic_weak_score=0.1,
        missing_skills=[],
        cross_encoder_score=0.9,
    )
    expl2 = RankingExplanationOut(
        skills_match_ratio=0.5,
        experience_match=0.5,
        education_match=0.5,
        heuristic_weak_score=0.5,
        missing_skills=["postgresql"],
        cross_encoder_score=0.55,
    )
    r1 = _row(1, "A", "Engineer", "backend", "A1", 0.9, 6.0, "bachelor", expl1)
    r2 = _row(2, "B", "Developer", "backend", "B1", 0.55, 2.0, "bachelor", expl2)
    text = build_top_candidate_insight_paragraph(job, [(r1, c1), (r2, c2)])
    assert "Compared with B" in text or "compared with b" in text.lower()
