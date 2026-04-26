from __future__ import annotations

import pytest

from src.matching.weak_score import (
    clean_skill_fragment,
    exp_score,
    overlap_ratio,
    parse_skill_str,
    weak_score,
)


def test_parse_skill_str():
    s = parse_skill_str("Python, SQL, AWS")
    assert "python" in s and "sql" in s


def test_clean_skill_fragment_drops_truncated_linkedin_qualifier():
    assert clean_skill_fragment("figma(software") is None
    assert clean_skill_fragment("Figma (software)") == "figma"


def test_parse_skill_str_truncated_figma_software_no_bare_figma():
    s = parse_skill_str("Python, figma(software, SQL")
    assert "python" in s and "sql" in s
    assert "figma" not in s


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
