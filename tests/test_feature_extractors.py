from __future__ import annotations

from src.parsing.feature_extractors import estimate_years_experience


def test_estimate_years_experience_ignores_education_ranges():
    txt = """
JOHN DOE
WORK EXPERIENCE
Backend Engineer — ACME Corp
2020-2024 Worked on APIs

EDUCATION
BS Computer Science 2017-2021 University of Somewhere
"""
    assert estimate_years_experience(txt, current_year=2026) == 4.0


def test_estimate_years_experience_prefers_years_phrase():
    txt = "Profile: 6+ years experience in backend development.\nEDUCATION 2017-2021 BS."
    assert estimate_years_experience(txt, current_year=2026) == 6.0


def test_estimate_years_experience_bullet_section_header():
    txt = """
JANE DOE
• Work Experience
Backend Engineer at ACME
2020 to 2024 — platform team

• Education
BS 2016-2020 State University
"""
    assert estimate_years_experience(txt, current_year=2026) == 4.0


def test_estimate_years_experience_slash_dates():
    txt = """
WORK EXPERIENCE
ACME — 01/2020 – 06/2024 Senior Engineer

EDUCATION
University 09/2015 - 05/2019
"""
    # Month-precision ranges return fractional years.
    assert estimate_years_experience(txt, current_year=2026) == 4.4


def test_estimate_years_experience_over_n_years_phrase():
    txt = "Summary: Over 12 years of Python. EDUCATION 2010-2014."
    assert estimate_years_experience(txt, current_year=2026) == 12.0


def test_experience_continues_past_inline_skills_subheading():
    """'Skills' must not end the experience section (common resume layout)."""
    txt = """
WORK EXPERIENCE
Software Engineer — ACME
2020-2024

Skills: Python, AWS

Senior Engineer — OTHER CO
2016-2019

EDUCATION
BS Computer Science 2012-2016 Some University
"""
    assert estimate_years_experience(txt, current_year=2026) == 7.0


def test_collapsed_line_pdf_style_with_injected_newlines():
    txt = (
        "JOHN DOE WORK EXPERIENCE ACME INC engineer 2018-2024 built apis "
        "EDUCATION BS 2014-2018 State University"
    )
    assert estimate_years_experience(txt, current_year=2026) == 6.0


def test_ocr_spaced_year_digits():
    txt = "WORK EXPERIENCE\nACME 2 0 1 8 – 2 0 2 4 backend\nEDUCATION 2010-2014"
    assert estimate_years_experience(txt, current_year=2026) == 6.0


def test_overlapping_ranges_are_merged_not_summed():
    # Overlap: 2020-2024 and 2022-2026 should count as 6 years total (2020→2026), not 8.
    txt = """
WORK EXPERIENCE
Engineer — A
2020-2024
Engineer — B
2022-2026
"""
    assert estimate_years_experience(txt, current_year=2026) == 6.0


def test_no_experience_header_does_not_count_education_ranges():
    # No explicit "work experience" header; should not infer from education-only date ranges.
    txt = """
EDUCATION
BS Computer Science 2016-2020 State University (GPA 3.8)
MS Data Science 2020-2022 Some College
"""
    assert estimate_years_experience(txt, current_year=2026) == 0.0


def test_skills_heading_ends_experience_section():
    # Standalone "Skills" heading should end the experience section.
    txt = """
WORK EXPERIENCE
Engineer — A
2020-2024

SKILLS
Python, AWS

Engineer — B
2016-2019
"""
    assert estimate_years_experience(txt, current_year=2026) == 4.0


def test_collapsed_pdf_inserts_break_before_experience_heading():
    """Some PDFs glue EDUCATION and EXPERIENCE without newlines."""
    txt = (
        "ALI J EDUCATION BS CS 2016-2020 University EXPERIENCE QA Engineer ACME 2020--2024 "
        "automation EDUCATION details"
    )
    assert estimate_years_experience(txt, current_year=2026) == 4.0


def test_double_hyphen_year_range():
    txt = """
WORK EXPERIENCE
Engineer — ACME
2020--2024

EDUCATION
2010-2014
"""
    assert estimate_years_experience(txt, current_year=2026) == 4.0


def test_working_experience_heading():
    txt = "PROFILE SUMMARY WORKING EXPERIENCE ACME 2019-2023 EDUCATION BS 2015-2019"
    assert estimate_years_experience(txt, current_year=2026) == 4.0

