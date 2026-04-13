from __future__ import annotations

from src.parsing.name_extractor import extract_name_from_raw, guess_name_from_filename_stem


def test_name_label_colon():
    txt = """Full Name: Ali Janjua
QA Engineer
Lahore
"""
    assert extract_name_from_raw(txt) == "Ali Janjua"


def test_pipe_name_before_title():
    txt = """Ali Janjua | Senior QA Engineer | +92 300 0000000
Summary line
"""
    assert extract_name_from_raw(txt) == "Ali Janjua"


def test_pipe_title_before_name():
    txt = """Senior Software Engineer | Maria Garcia | maria@email.com
"""
    # Prefer first chunk only if it's not a title; "Maria Garcia" is third chunk — actually second after split
    # Line: chunk1 Senior Software Engineer (title), chunk2 Maria Garcia, chunk3 email
    out = extract_name_from_raw(txt)
    assert out == "Maria Garcia"


def test_dr_prefix():
    txt = "Dr. Ayesha Khan\nConsultant\n"
    assert extract_name_from_raw(txt) == "Ayesha Khan"


def test_hyphenated_surname():
    txt = "Jean-Luc Picard\nCaptain\n"
    assert extract_name_from_raw(txt) == "Jean-Luc Picard"


def test_skips_pure_title_line():
    txt = """Professional Summary
Senior Backend Engineer with 5 years
John Smith
"""
    # "John Smith" might be line 3 — but "Professional Summary" bad? not in RE_BAD_LINE_HINT exactly
    # Line 2 has engineer — chunks might be whole line
    assert extract_name_from_raw(txt) == "John Smith"


def test_empty_when_only_title():
    txt = """Software Engineer
Python, AWS
"""
    assert extract_name_from_raw(txt) == ""


def test_collapsed_whitespace_pipe_header_like_stored_raw_text():
    """After strip_pii, newlines become spaces; pipes often remain."""
    txt = "Ali Janjua | Senior QA Engineer [PHONE] Lahore Pakistan"
    assert extract_name_from_raw(txt) == "Ali Janjua"


def test_rejects_soft_skill_heading_not_name():
    assert extract_name_from_raw("Time management\nCommunication\n") == ""


def test_rejects_company_software_suffix():
    assert extract_name_from_raw("Contour Software\nKarachi\n") == ""


def test_rejects_ai_topic_heading():
    assert extract_name_from_raw("Artificial Intelligence\nTensorFlow\n") == ""


def test_skill_heading_then_real_name_still_works():
    txt = """Time management
Ali Janjua
QA Engineer
"""
    assert extract_name_from_raw(txt) == "Ali Janjua"


def test_rejects_finance_analyst_as_name():
    assert extract_name_from_raw("Finance Analyst\nSkills: Excel\n") == ""


def test_guess_name_from_filename_stem_two_words():
    assert guess_name_from_filename_stem("Jane_Doe") == "Jane Doe"
    assert guess_name_from_filename_stem("Jane_Doe_Resume") == "Jane Doe"


def test_guess_name_from_filename_rejects_resume_stem():
    assert guess_name_from_filename_stem("My_Resume_Final") == ""
    assert guess_name_from_filename_stem("1775595018794_19DF") == ""
