from __future__ import annotations

from src.preprocessing.pii import contains_pii, extract_primary_email, strip_pii, strip_pii_keep_newlines


def test_strip_email():
    t = "Contact me at user@example.com today"
    out = strip_pii(t)
    assert "user@example.com" not in out
    assert "[EMAIL]" in out


def test_contains_pii():
    assert contains_pii("x@y.co")
    assert not contains_pii("no pii here")


def test_strip_pii_keep_newlines():
    t = "Line one\nuser@test.com\nLine three"
    out = strip_pii_keep_newlines(t)
    assert "user@test.com" not in out
    assert "[EMAIL]" in out
    assert "\n" in out
    assert "Line one" in out and "Line three" in out


def test_extract_primary_email_labeled():
    t = "Jane Doe\nE-mail: jane.doe@company.io\nSkills: Python"
    assert extract_primary_email(t) == "jane.doe@company.io"


def test_extract_primary_email_mailto():
    # Avoid reserved example.* domains — those are skipped as placeholder addresses.
    t = "See also <mailto:hire_me@acme.jobs> for contact."
    assert extract_primary_email(t) == "hire_me@acme.jobs"


def test_extract_primary_email_reach_me_at_not_obfuscation():
    """Literal ' at ' before an address must not become a false @ (regression guard)."""
    t = "Reach me at ahmad.ali@acme.jobs for references."
    assert extract_primary_email(t) == "ahmad.ali@acme.jobs"

def test_extract_primary_email_ocr_line_break_inside_address():
    t = "Jane Smith\njane.smith@\ngmail.com\nSkills: Python"
    assert extract_primary_email(t) == "jane.smith@gmail.com"
