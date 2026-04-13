from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.services.candidate_competition_score import (  # type: ignore[reportMissingImports]
    compute_competition_payloads,
    compute_profile_scores_0_100,
)


def _ensure_stub_bcrypt() -> None:
    """Importing api.routers.candidates pulls dependencies → security → bcrypt."""
    if "bcrypt" in sys.modules:
        return
    bc = types.ModuleType("bcrypt")

    def _gensalt(*_a, **_k):
        return b"$2b$12$stubstubstubstubstubstubu"

    def _hashpw(_p, _s):
        return b"$2b$12$stubstubstubstubstubstubu"

    def _checkpw(_p, _h):
        return True

    bc.gensalt = _gensalt
    bc.hashpw = _hashpw
    bc.checkpw = _checkpw
    sys.modules["bcrypt"] = bc


def _ensure_stub_jose() -> None:
    """Same import chain loads api.security → python-jose."""
    if "jose" in sys.modules:
        return

    class JWTError(Exception):
        pass

    jwt_sub = types.ModuleType("jose.jwt")

    def _encode(*_a, **_k):
        return "stub"

    def _decode(*_a, **_k):
        return {}

    jwt_sub.encode = _encode
    jwt_sub.decode = _decode
    sys.modules["jose.jwt"] = jwt_sub

    jose_mod = types.ModuleType("jose")
    jose_mod.JWTError = JWTError
    jose_mod.jwt = jwt_sub
    sys.modules["jose"] = jose_mod


def _c(y, skills, deg, cert="", eid="x"):
    return SimpleNamespace(
        id=uuid4(),
        years_experience=y,
        skills=skills,
        highest_degree=deg,
        certifications=cert,
        external_id=eid,
        title="Eng",
        raw_text="body",
    )


@pytest.fixture
def candidates_client(monkeypatch, tmp_path):
    """
    Minimal app (candidates routes only) so this module does not import api.main / slowapi.
    """
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    _ensure_stub_bcrypt()
    _ensure_stub_jose()

    monkeypatch.setenv("REZUME_COMPETITION_SKIP_JOB_FIT", "true")
    monkeypatch.setenv("REZUME_TESTING", "1")
    monkeypatch.setenv("SKIP_MODEL_WARMUP", "true")
    from api.config import get_settings  # type: ignore[reportMissingImports]

    get_settings.cache_clear()

    from api.database import Base, get_db  # type: ignore[reportMissingImports]
    from api.routers import candidates as candidates_router  # type: ignore[reportMissingImports]

    app = FastAPI()
    app.include_router(candidates_router.router, prefix="/api/v1")

    db_path = tmp_path / "pytest_candidate_competition.db"
    eng = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    SessionLocal = sessionmaker(bind=eng)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_profile_percentiles_order_by_experience():
    cohort = [
        _c(0.0, "a", "BS", ""),
        _c(5.0, "a", "BS", ""),
        _c(10.0, "a", "BS", ""),
    ]
    scores = compute_profile_scores_0_100(cohort)
    assert scores[0] < scores[1] < scores[2]


def test_profile_more_skills_ranks_higher_when_years_equal():
    cohort = [
        _c(2.0, "python", "BS", ""),
        _c(2.0, "python, java, go, rust", "BS", ""),
    ]
    scores = compute_profile_scores_0_100(cohort)
    assert scores[1] > scores[0]


def test_competition_combines_profile_and_job_average(monkeypatch):
    """Avoid loading torch: stub mean job match (60 on 0–100) vs two imaginary jobs."""
    monkeypatch.setenv("REZUME_COMPETITION_SKIP_JOB_FIT", "0")
    cohort = [_c(3.0, "x,y", "Bachelor", "AWS")]

    def fake_avg_job_match(_db, cands):
        return [60.0] * len(cands), 2

    monkeypatch.setattr(
        "api.services.candidate_competition_score.compute_avg_job_match_0_100",
        fake_avg_job_match,
    )

    out = compute_competition_payloads(SimpleNamespace(), cohort)
    cid = cohort[0].id
    assert out[cid]["profile_percentile_score"] == 50.0
    assert out[cid]["avg_job_match_score"] == 60.0
    assert out[cid]["competition_score"] == 55.0  # 0.5 * 50 + 0.5 * 60


def test_scoreboard_includes_competition_score(candidates_client, monkeypatch):
    monkeypatch.setenv("REZUME_COMPETITION_SKIP_JOB_FIT", "true")
    from api.config import get_settings  # type: ignore[reportMissingImports]

    get_settings.cache_clear()
    r = candidates_client.post(
        "/api/v1/candidates",
        json={
            "external_id": "c_comp_1",
            "full_name": "A",
            "title": "Dev",
            "skills": "a,b",
            "years_experience": 4,
            "highest_degree": "BS CS",
        },
    )
    assert r.status_code == 201
    r2 = candidates_client.get("/api/v1/candidates/scoreboard")
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0].get("competition_score") is not None
    assert rows[0].get("profile_percentile_score") is not None

    r3 = candidates_client.get("/api/v1/candidates")
    assert r3.status_code == 200
    assert "competition_score" not in r3.json()[0]
