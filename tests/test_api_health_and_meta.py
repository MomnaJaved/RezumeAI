from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_meta_models(client):
    r = client.get("/api/v1/meta/models")
    assert r.status_code == 200
    data = r.json()
    assert "versions" in data
    assert "cross_encoder" in data["versions"]


def test_meta_stats_empty_db(client):
    r = client.get("/api/v1/meta/stats")
    assert r.status_code == 200
    assert r.json()["candidates_total"] == 0


def test_meta_activity_empty_db(client):
    r = client.get("/api/v1/meta/activity")
    assert r.status_code == 200
    data = r.json()
    assert "notifications" in data
    assert data["notifications"] == []


def test_meta_dashboard_notifications_shape(client):
    r = client.get("/api/v1/meta/dashboard")
    assert r.status_code == 200
    notes = r.json().get("notifications")
    assert isinstance(notes, list)


def test_meta_dashboard_widgets_shape(client):
    r = client.get("/api/v1/meta/dashboard/widgets")
    assert r.status_code == 200
    data = r.json()
    assert "pipeline" in data and isinstance(data["pipeline"], list)
    assert "jobs_chart" in data and "segments" in data["jobs_chart"]
    assert "candidate_preview" in data and isinstance(data["candidate_preview"], list)
