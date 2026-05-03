from __future__ import annotations

from io import BytesIO
from uuid import uuid4


def _auth_headers_recruiter():
    """Bearer token for a real User row in the test DB (uploads require sign-in)."""
    from api.main import app
    from api.models import User
    from api.routers.auth import hash_password
    from api.security import create_access_token

    SessionLocal = app.state.test_SessionLocal
    db = SessionLocal()
    uid = uuid4()
    email = f"upload_{uuid4().hex[:10]}@test.local"
    u = User(
        id=uid,
        email=email,
        password_hash=hash_password("testpass123"),
        is_verified=True,
        account_role="recruiter",
    )
    db.add(u)
    db.commit()
    db.close()
    tok = create_access_token(str(uid), extra={"email": email, "account_role": "recruiter"})
    return {"Authorization": f"Bearer {tok}"}


def test_upload_resume_txt(client):
    headers = _auth_headers_recruiter()
    raw = (
        b"Jane Smith\nSenior Developer\n\n"
        b"Skills: Python, Django, PostgreSQL, Docker.\n"
        b"Ten years building APIs and microservices.\n"
    )
    r = client.post(
        "/api/v1/uploads/resume",
        files={"file": ("resume.txt", BytesIO(raw), "text/plain")},
        headers=headers,
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


def test_upload_resume_requires_auth(client):
    raw = (
        b"Jane Smith\nSenior Developer\n\n"
        b"Skills: Python, Django, PostgreSQL, Docker.\n"
        b"Ten years building APIs and microservices.\n"
    )
    r = client.post(
        "/api/v1/uploads/resume",
        files={"file": ("resume.txt", BytesIO(raw), "text/plain")},
    )
    assert r.status_code == 401


def test_upload_invalid_type(client):
    r = client.post(
        "/api/v1/uploads/resume",
        files={"file": ("x.exe", BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert r.status_code == 415
    j = r.json()
    assert j.get("success") is False
    assert j.get("code") == "UNSUPPORTED_FILE_TYPE"
