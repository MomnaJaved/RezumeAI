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


def test_extract_education_strips_linkedin_fluff_and_mojibake():
    """LinkedIn-style education blocks often include activities, skill footers, and first-person blurbs."""
    bad_en = "\u2013".encode("utf-8").decode("cp1252")
    text = f"""Education
High Impact Skills Development Program in Artificial Intelligence, Data Science, (NUST), Islamabad
BS-AI, Artificial Intelligence
Jun 2023{bad_en}Nov 2023
Grade: pass
Activities and societies: Football
Hello there, I underwent a 6-month AI and data science training program at NUST and now I am a BS student at SZABIST in Pakistan.
Computer Vision, Data Visualization and +9 skills
SZABIST University - Islamabad Campus — Bachelor's degree, AI
Feb 2024{bad_en}Present
Activities and societies: coding
sports
Artificial Intelligence (AI), Computer Vision and +9 skills
"""
    out = extract_education(text)
    lines = (out.get("education_lines") or "").split(" | ")
    blob = " ".join(lines).lower()
    assert "activities and societies" not in blob
    assert "hello there" not in blob
    assert "underwent" not in blob
    assert "+9 skills" not in blob
    assert "grade: pass" not in blob
    assert "football" not in blob and "sports" not in blob
    assert " coding " not in f" {blob} "  # standalone activities line, not substring
    assert "szabist" in blob or "nust" in blob or "bs-ai" in blob
    assert len(lines) <= 6


def test_estimate_years_ignores_years_related_ad_copy():
    """LinkedIn-style ads use 'N years related…' — must not become tenure."""
    text = """
Don't want to see this
13 years related to your experience with ads
Your feedback will help us improve your experience
"""
    assert estimate_years_experience(text, current_year=2026) == 0.0


def test_estimate_years_loose_phrase_still_counts_with_clear_tenure_tail():
    text = "Senior engineer with 13 years of experience shipping backend systems."
    y = estimate_years_experience(text, current_year=2026)
    assert y >= 13.0


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
