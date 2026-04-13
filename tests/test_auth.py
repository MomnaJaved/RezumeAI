from __future__ import annotations

from uuid import uuid4


def test_register_and_login(client):
    email = f"user_{uuid4().hex[:10]}@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "longpassword1"},
    )
    assert r.status_code == 200
    tok = r.json()["access_token"]
    assert tok

    r2 = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "longpassword1"},
    )
    assert r2.status_code == 200
    assert r2.json()["access_token"]
