from __future__ import annotations

import pytest

from api.services.resume_ingest import parse_upload


def test_parse_upload_txt():
    body = b"John Doe\n\nSoftware Engineer\n\nPython, SQL experience for ten years in backend systems."
    out = parse_upload("cv.txt", body)
    assert out["text_len"] >= 80
    assert "external_id" in out


def test_parse_upload_rejects_huge():
    with pytest.raises(ValueError, match="too large|large"):
        parse_upload("x.txt", b"x" * (20 * 1024 * 1024))
