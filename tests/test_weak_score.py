from __future__ import annotations

import pytest

from src.matching.weak_score import (
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
