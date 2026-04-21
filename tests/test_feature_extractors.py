from __future__ import annotations

from src.parsing.feature_extractors import estimate_years_experience, extract_education


def test_extract_education_truncates_pipe_separated_skills_tail():
    """PDF-style single line: degree then | Technical Skills | bullet tech — keep only education."""
    text = """
EDUCATION
Bahria University — Bachelor of Science in Computer Science | 2022 – 2026 | Technical Skills | Programming & Development | ● JavaScript (ES6+), TypeScript, Python
"""
    r = extract_education(text)
    assert "Bahria" in r["education_lines"]
    assert "Bachelor" in r["education_lines"] or "Computer Science" in r["education_lines"]
    assert "Technical Skills" not in r["education_lines"]
    assert "JavaScript" not in r["education_lines"]
    assert "Programming" not in r["education_lines"]


def test_extract_education_truncates_with_zwsp_before_skills_heading():
    """PDFs sometimes insert zero-width chars so '| Technical' no longer matches a simple pipe regex."""
    zw = "\u200b"
    text = f"""
EDUCATION
Bahria University — BS Computer Science | 2022 – 2026 |{zw} Technical Skills |{zw} ● JavaScript, Python
"""
    r = extract_education(text)
    assert "Bahria" in r["education_lines"]
    assert "Technical Skills" not in r["education_lines"]
    assert "JavaScript" not in r["education_lines"]


def test_extract_education_truncates_unpiped_technical_skills_after_year():
    text = """
EDUCATION
Bahria University — Bachelor of Science 2022 – 2026 Technical Skills JavaScript, React
"""
    r = extract_education(text)
    assert "Bahria" in r["education_lines"]
    assert "Technical Skills" not in r["education_lines"]
    assert "JavaScript" not in r["education_lines"]


def test_extract_education_full_cv_tail_removed_and_no_trailing_pipe():
    """Real-world glued line: degree + years + full skills stack (finalize pass)."""
    text = """
EDUCATION
Bahria University — Bachelor of Science in Computer Science | 2022 – 2026 | Technical Skills | Programming & Development | ● JavaScript (ES6+), TypeScript, Python | ● React.js, Node.js, NestJS, Express.js | Web Technologies | ● HTML5, CSS, Tailwind CSS
"""
    r = extract_education(text)
    assert "Bahria" in r["education_lines"]
    assert "2022" in r["education_lines"] or "2026" in r["education_lines"]
    assert "Technical Skills" not in r["education_lines"]
    assert "JavaScript" not in r["education_lines"]
    assert "NestJS" not in r["education_lines"]
    assert not r["education_lines"].rstrip().endswith("|")


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
