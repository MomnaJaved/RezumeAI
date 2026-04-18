from __future__ import annotations

from src.parsing.feature_extractors import estimate_years_experience


def test_estimate_years_without_experience_header_role_lines():
    text = """
Jane Doe
Senior Software Engineer

Acme Corp   Jan 2018 – Dec 2021
Built APIs and microservices.

Beta Technologies   Jan 2022 – Present
Staff engineer, platform team.
"""
    y = estimate_years_experience(text, current_year=2026)
    assert y >= 7.0


def test_estimate_years_skips_education_only_ranges_without_header():
    text = """
Alex Lee

University of Science 2014 – 2018
Bachelor of Science, Statistics
"""
    y = estimate_years_experience(text, current_year=2026)
    assert y == 0.0


def test_estimate_years_singular_year_experience_in_summary_no_header():
    text = """
Jordan Lee
Software Developer

Profile
Passionate engineer with 1 year experience shipping production APIs and services.
Skills: Python, PostgreSQL
"""
    y = estimate_years_experience(text, current_year=2026)
    assert y >= 1.0


def test_estimate_years_years_of_professional_experience_phrase():
    text = """
Summary
Results-driven developer with 4 years of professional experience across fintech and SaaS.
"""
    y = estimate_years_experience(text, current_year=2026)
    assert y >= 4.0


def test_estimate_years_with_1_year_experience_colloquial():
    text = "Motivated candidate with 1 year experience in Java and Spring Boot."
    y = estimate_years_experience(text, current_year=2026)
    assert y >= 1.0


def test_estimate_years_narrative_operations_cv_not_vetoed_by_education_below():
    """Phrase 'has 2.5 years of experience' must not be dropped when EDUCATION appears later."""
    text = """
SKILLS
Operations Support, Coordination, Reporting
EXPERIENCE
Usman Khan has 2.5 years of experience in operations support roles.
EDUCATION
BS Business Administration – Karachi University
"""
    y = estimate_years_experience(text, current_year=2026)
    assert y >= 2.4
