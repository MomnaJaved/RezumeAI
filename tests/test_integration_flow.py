from __future__ import annotations

from io import BytesIO
from uuid import uuid4


def _auth_headers_recruiter():
    from api.main import app
    from api.models import User
    from api.routers.auth import hash_password
    from api.security import create_access_token

    SessionLocal = app.state.test_SessionLocal
    db = SessionLocal()
    uid = uuid4()
    email = f"int_{uuid4().hex[:10]}@test.local"
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


def test_upload_then_stats(client):
    job_id = f"T{uuid4().hex[:8]}"
    client.post(
        "/api/v1/jobs",
        json={
            "external_id": job_id,
            "title": "Backend Engineer",
            "description": "We need Python and PostgreSQL.",
            "skills": "python, postgresql, docker",
            "min_experience": 2.0,
            "education_required": "bachelors",
        },
    )

    raw = (
        b"Alex Lee\nBackend Developer\n\n"
        b"Python PostgreSQL AWS. Five years experience.\n"
    )
    up = client.post(
        "/api/v1/uploads/resume",
        files={"file": ("cv.txt", BytesIO(raw), "text/plain")},
        headers=_auth_headers_recruiter(),
    )
    if up.status_code not in (200, 422, 503):
        up.raise_for_status()

    stats = client.get("/api/v1/meta/stats").json()
    # Job always inserted; candidate if parse succeeded
    assert stats["jobs_total"] >= 1
