from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("REZUME_TESTING", "1")
    monkeypatch.setenv("SKIP_MODEL_WARMUP", "true")
    from api.config import get_settings

    get_settings.cache_clear()

    from api.database import Base, get_db
    from api.main import app

    db_path = tmp_path / "pytest.db"
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
    # Lets tests insert a User row and mint a JWT against the same DB session factory.
    app.state.test_SessionLocal = SessionLocal
    from fastapi.testclient import TestClient

    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "test_SessionLocal"):
            delattr(app.state, "test_SessionLocal")
