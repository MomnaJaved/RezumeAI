from __future__ import annotations

from io import BytesIO
from uuid import uuid4

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
    )
    if up.status_code not in (200, 422, 503):
        up.raise_for_status()

    stats = client.get("/api/v1/meta/stats").json()
    # Job always inserted; candidate if parse succeeded
    assert stats["jobs_total"] >= 1
