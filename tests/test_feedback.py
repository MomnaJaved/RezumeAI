from __future__ import annotations

from uuid import uuid4


def test_ranking_selection_feedback(client):
    jid = f"FJ{uuid4().hex[:6].upper()}"
    cid = f"FC{uuid4().hex[:6].upper()}"
    client.post(
        "/api/v1/jobs",
        json={
            "external_id": jid,
            "title": "Engineer",
            "description": "Python",
            "skills": "python",
        },
    )
    client.post(
        "/api/v1/candidates",
        json={
            "external_id": cid,
            "full_name": "Test",
            "raw_text": "Python developer",
            "skills": "python",
        },
    )
    r = client.post(
        "/api/v1/feedback/ranking-selection",
        json={
            "job_external_id": jid,
            "candidate_external_id": cid,
            "action": "selected",
            "rank_position_shown": 2,
            "model_score_at_feedback": 0.91,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["action"] == "selected"
    assert data["candidate_external_id"] == cid

    s = client.get("/api/v1/feedback/ranking-selection/summary")
    assert s.json()["human_feedback_events_total"] >= 1

    cand = client.get(f"/api/v1/candidates/by-external/{cid}")
    assert cand.status_code == 200
    assert cand.json()["status"] == "selected"
