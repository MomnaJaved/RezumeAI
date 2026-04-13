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
