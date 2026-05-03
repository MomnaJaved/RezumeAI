from __future__ import annotations

import pytest

from src.matching.weak_score import (
    compute_experience_score,
    compute_final_score,
    compute_skill_overlap,
    normalize_skills,
    exp_score,
    overlap_ratio,
    parse_skill_str,
    weak_score,
)


def test_parse_skill_str():
    s = parse_skill_str("Python, SQL, AWS")
    assert "python" in s and "sql" in s


def test_overlap_ratio():
    job = parse_skill_str("a, b, c")
    cand = parse_skill_str("a, b")
    assert overlap_ratio(job, cand) == pytest.approx(2 / 3)


def test_exp_score_meets_min():
    assert exp_score(5.0, 3.0) == 1.0
    assert exp_score(1.5, 3.0) == pytest.approx(0.5)


def test_weak_score_range():
    job = parse_skill_str("java, spring")
    cand = parse_skill_str("java, kotlin")
    w = weak_score(job, cand, 1.0, 0.5)
    assert 0.0 <= w <= 1.0


def test_skill_normalization_expands_synonyms():
    # Candidate has "Kafka", job asks for "Message Queues"
    job = parse_skill_str("message queues")
    cand = parse_skill_str("kafka")
    assert compute_skill_overlap(job, cand) == pytest.approx(1.0)


def test_experience_score_calibration():
    assert compute_experience_score(5, 4, 6) == pytest.approx(1.0)
    assert compute_experience_score(10, 4, 6) == pytest.approx(0.9)
    assert compute_experience_score(3.2, 4, 6) == pytest.approx(0.7)
    assert compute_experience_score(1, 4, 6) == pytest.approx(0.4)


def test_final_score_additive_no_multiplicative_collapse():
    # A strong semantic match should not be crushed by partial skill overlap.
    s = compute_final_score(semantic_similarity=0.9, skill_overlap=0.5, experience_score=1.0)
    assert s > 0.70
