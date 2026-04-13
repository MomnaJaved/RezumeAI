from __future__ import annotations

from fastapi.testclient import TestClient


def test_bulk_ingestion_creates_rows_and_status(client: TestClient):
    # Use plain text files to avoid OCR dependencies.
    files = [
        (
            "files",
            (
                "a.txt",
                (
                    b"John Doe\nPython developer\nSkills: python, fastapi, pandas, postgres\n"
                    b"Experience: 3 years\nProjects: built APIs, ETL pipelines, dashboards.\n"
                    b"Summary: motivated engineer looking for backend roles.\n"
                ),
                "text/plain",
            ),
        ),
        (
            "files",
            (
                "b.txt",
                (
                    b"Jane Smith\nData analyst\nSkills: sql, power bi, excel, statistics\n"
                    b"Experience: 2 years\nProjects: reporting, KPI dashboards, A/B analysis.\n"
                    b"Summary: detail oriented analyst with strong communication.\n"
                ),
                "text/plain",
            ),
        ),
    ]
    r = client.post("/api/v1/ingestions/bulk", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "batch_id" in body
    assert len(body["accepted"]) == 2

    batch_id = body["batch_id"]
    # Poll a few times: BackgroundTasks runs after response in TestClient, so this is usually immediate.
    for _ in range(10):
        s = client.get(f"/api/v1/ingestions/batch/{batch_id}")
        assert s.status_code == 200, s.text
        st = s.json()
        if st["done"] == 2:
            break
    assert st["done"] == 2
    assert st["failed"] == 0


def test_text_ingestion_works(client: TestClient):
    r = client.post(
        "/api/v1/ingestions/text",
        json={"text": "Resume\nBackend engineer\nSkills: node.js, postgres\nExperience: 4 years", "source": "extension"},
    )
    assert r.status_code == 200, r.text
    ing = r.json()
    assert ing["status"] in ("queued", "processing", "done")
    # Fetch by id
    g = client.get(f"/api/v1/ingestions/{ing['id']}")
    assert g.status_code == 200

