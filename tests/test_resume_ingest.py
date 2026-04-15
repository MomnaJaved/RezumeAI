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
    body = (filler * 3 + "Reach me at ahmad.ali@example.com for references.\n").encode()
    out = parse_upload("cv.txt", body)
    assert out["contact_email"] == "ahmad.ali@example.com"
    assert out["full_name"] == "Ahmad Ali"


def test_parse_upload_rejects_huge():
    with pytest.raises(ValueError, match="too large|large"):
        parse_upload("x.txt", b"x" * (20 * 1024 * 1024))
