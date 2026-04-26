from __future__ import annotations

import pytest

pytest.importorskip("torch")

from api.services.resume_ingest import parse_upload


def test_parse_upload_txt():
    body = b"John Doe\n\nSoftware Engineer\n\nPython, SQL experience for ten years in backend systems."
    out = parse_upload("cv.txt", body)
    assert out["text_len"] >= 80
    assert "external_id" in out
    assert out["full_name"] == "John Doe"


def test_parse_upload_name_from_email_when_header_missing():
    filler = (
        "Software Engineer with extensive experience in backend development, APIs, "
        "databases, and cloud infrastructure. Deep hands-on work across the stack.\n"
    )
    body = (filler * 3 + "Reach me at ahmad.ali@acme.jobs for references.\n").encode()
    out = parse_upload("cv.txt", body)
    assert out["contact_email"] == "ahmad.ali@acme.jobs"
    assert out["full_name"] == "Ahmad Ali"


def test_parse_upload_rejects_huge():
    with pytest.raises(ValueError, match="too large|large"):
        parse_upload("x.txt", b"x" * (20 * 1024 * 1024))


def test_parse_upload_strips_resume_prose_from_skills_header():
    """Extension sometimes saves one long `Skills:` line with experience + location noise."""
    skills_blob = (
        "skills postgresql oauth, postgresql oauth, riyadh, saudi arabia â· on-site, "
        "hospital data with python (scikit-learn, xgboost, achieving up to 95%, accuracy, "
        "backend) and next.js (frontend, integrating ai apis (openai, hugging, modules, power bi dashboards, "
        "and salesforce crm, supporting data-driven, reporting and cross-functional business operations, "
        "artificial intelligence (ai, fastapi and +4 skills, founder, zero limit â· self-employed, "
        "postgresql, oauth, python, next.js, salesforce, crm, reporting, fastapi, c++, power bi, "
        "business operations, meta ads, machine learning, scikit-learn"
    )
    filler = "Summary line with enough characters for minimum length requirement here.\n" * 5
    body = (f"Skills: {skills_blob}\n\n" + filler + "contact@example.com\n").encode("utf-8")
    out = parse_upload("muhammad ahmad aslam.txt", body)
    sk = (out.get("skills") or "").lower()
    assert "postgresql" in sk or "oauth" in sk
    assert "riyadh" not in sk
    assert "on-site" not in sk
    assert "self-employed" not in sk
    assert "achieving up" not in sk
    assert "cross-functional" not in sk
    assert "hospital data" not in sk
    assert "business operations" not in sk


def test_parse_upload_merges_explicit_skills_header():
    """Chrome extension prepends `Skills: ...` above noisy LinkedIn text; keep those tokens."""
    filler = (
        "Talent Solutions\nAbout\nActivity\nExperience\n"
        "Software Engineer with extensive experience in backend development, APIs, "
        "databases, and cloud infrastructure.\n"
    )
    body = (
        "Skills: Python, Django, PostgreSQL\n\n"
        + filler * 4
        + "Reach me at jane.doe@example.com.\n"
    ).encode("utf-8")
    out = parse_upload("linkedin_export.txt", body)
    sk = (out.get("skills") or "").lower()
    assert "python" in sk
    assert "django" in sk
    assert "postgresql" in sk
