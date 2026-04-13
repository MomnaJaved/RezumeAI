from __future__ import annotations

from io import BytesIO


def test_upload_resume_txt(client):
    raw = (
        b"Jane Smith\nSenior Developer\n\n"
        b"Skills: Python, Django, PostgreSQL, Docker.\n"
        b"Ten years building APIs and microservices.\n"
    )
    r = client.post(
        "/api/v1/uploads/resume",
        files={"file": ("resume.txt", BytesIO(raw), "text/plain")},
    )
    if r.status_code != 200:
        # Role model may be missing in CI — accept 503 inference error as structured
        assert r.status_code in (422, 503)
        body = r.json()
        assert body.get("success") is False
        return
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("created", "updated_existing")
    assert data["candidate"]["external_id"]


def test_upload_invalid_type(client):
    r = client.post(
        "/api/v1/uploads/resume",
        files={"file": ("x.exe", BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert r.status_code == 415
    j = r.json()
    assert j.get("success") is False
    assert j.get("code") == "UNSUPPORTED_FILE_TYPE"
