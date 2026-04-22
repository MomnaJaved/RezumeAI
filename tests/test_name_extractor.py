from __future__ import annotations

from src.parsing.name_extractor import (
    UNKNOWN_CANDIDATE,
    extract_name_from_email,
    extract_name_from_raw,
    guess_name_from_filename_stem,
    resolve_candidate_full_name,
)


def test_ocr_double_spaced_letter_name_header():
    """Tesseract often spaces letters and uses 2+ spaces between given and family name."""
    txt = "J o h n   S m i t h\nSenior Engineer\njohn.smith@example.com\n"
    assert extract_name_from_raw(txt) == "John Smith"


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

def test_comma_last_first_format():
    assert extract_name_from_raw("DOE, JANE\nSoftware Engineer\n") == "Jane Doe"


def test_all_caps_name_is_normalized():
    assert extract_name_from_raw("ALI JANJUA | QA Engineer | ali@email.com\n") == "Ali Janjua"


def test_header_contact_line_prefers_person_over_location():
    txt = """Senior Software Engineer | John Smith | Karachi, Pakistan | john@email.com
Summary
"""
    assert extract_name_from_raw(txt) == "John Smith"


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

def test_rejects_certification_line_as_name():
    assert extract_name_from_raw("AWS Certified Solutions Architect\nSkills: Python\n") == ""
    assert extract_name_from_raw("Certified Kubernetes Administrator\n") == ""


def test_guess_name_from_filename_stem_two_words():
    assert guess_name_from_filename_stem("Jane_Doe") == "Jane Doe"
    assert guess_name_from_filename_stem("Jane_Doe_Resume") == "Jane Doe"


def test_guess_name_from_filename_rejects_resume_stem():
    assert guess_name_from_filename_stem("My_Resume_Final") == ""
    assert guess_name_from_filename_stem("1775595018794_19DF") == ""
    assert guess_name_from_filename_stem("sample_resume") == ""


def test_extract_name_from_email_two_tokens():
    assert extract_name_from_email("ahmad.ali@gmail.com") == "Ahmad Ali"
    assert extract_name_from_email("Jane-Doe@company.org") == "Jane Doe"


def test_extract_name_from_email_rejects_single_token():
    assert extract_name_from_email("admin@company.org") == ""


def test_extract_name_from_email_rejects_skipped_prefix():
    assert extract_name_from_email("support@company.org") == ""


def test_resolve_candidate_full_name_order():
    raw = "Sara Khan\nData Analyst\n"
    name, src = resolve_candidate_full_name(raw, "other.person@x.com")
    assert name == "Sara Khan"
    assert src == "resume"


def test_resolve_candidate_full_name_falls_back_to_email():
    raw = "Machine Learning\nTensorFlow\nPyTorch\n"
    name, src = resolve_candidate_full_name(raw, "maria.garcia@x.com")
    assert name == "Maria Garcia"
    assert src == "email"


def test_resolve_candidate_full_name_unknown():
    raw = "x\ny\n"
    name, src = resolve_candidate_full_name(raw, "a@b.co")
    assert name == UNKNOWN_CANDIDATE
    assert src == "unknown"


def test_name_on_same_line_as_email_in_header():
    """Name + contact on one line; must not be skipped for having an @ in the line."""
    txt = "Ahsan Farhan Sherazi  ahsan@mail.com\nData Analyst\nSummary\n"
    assert extract_name_from_raw(txt) == "Ahsan Farhan Sherazi"


def test_name_before_phone_on_header_line():
    """Camera scans: name and PK phone on the same line, no email on that line."""
    txt = "Ahsan Farhan Sherazi +92-317-4497371\ndonothing\n"
    assert extract_name_from_raw(txt) == "Ahsan Farhan Sherazi"


def test_name_email_label_ocr_mangled_at():
    """OCR can leave ``Email:`` and domain but drop ``@`` on the same line as the name."""
    txt = "Ahsan Farhan Sherazi  E-mail: ahsanf@gmail.com  \nmore\n"
    assert extract_name_from_raw(txt) == "Ahsan Farhan Sherazi"


def test_name_with_email_label_and_long_local_part():
    """Printed CVs: name left, 'Email: local@...' (must not keep 'Email:' in the parsed name)."""
    line = "Ahsan Farhan Sherazi  Email: ahsanfarhansherazi02@gmail.com"
    # Long header line (must not be dropped by a short chunk length cap)
    long_line = "Ahsan Farhan Sherazi  Email: ahsanfarhansherazi02.verylongprefix@gmail.com"
    assert len(long_line) > 70
    for header in (line, long_line):
        txt = header + "\nlinkedin.com/in/ahsan-farhan\n+92-317-0000000\n"
        assert extract_name_from_raw(txt) == "Ahsan Farhan Sherazi"


def test_name_on_second_line_still_meets_min_score():
    """Legacy path (40 - line_index) can score 39; threshold must allow it if no other hit."""
    txt = "RESUME\nAhsan Farhan Sherazi\nData Analyst\n"
    assert extract_name_from_raw(txt) == "Ahsan Farhan Sherazi"


def test_strip_pii_collapse_loses_name_headers_for_resolve():
    """
    ``strip_pii`` collapses newlines to one long line, so the scan preview round-trip
    must not pass only that to ``resolve_candidate_full_name`` if we expect header names.
    """
    from src.parsing.ocr_normalize import normalize_resume_text_for_ocr
    from src.preprocessing.pii import strip_pii, strip_pii_keep_newlines

    body = (
        "A h s a n F a r h a n S h e r a z i\n"
        "Data Analyst\n"
        "ahsan@mail.com\n"
        + "Python " * 30
    )
    norm = normalize_resume_text_for_ocr(body)
    line_p = strip_pii_keep_newlines(norm)
    collapsed = strip_pii(norm)
    assert "\n" in line_p
    assert "\n" not in collapsed
    assert resolve_candidate_full_name(line_p, "")[0] == "Ahsan Farhan Sherazi"
    assert resolve_candidate_full_name(collapsed, "")[0] == UNKNOWN_CANDIDATE
