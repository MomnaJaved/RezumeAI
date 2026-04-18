from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.database import Base
from api.models import Candidate, Job, JobApplicant
from api.services import dashboard_widgets as dw


@pytest.fixture
def db_sess(tmp_path, monkeypatch):
    monkeypatch.setenv("REZUME_TESTING", "1")
    monkeypatch.setattr(dw, "_MAX_PIPELINE_PREVIEW_APPLICANTS", 2)
    db_path = tmp_path / "dash.db"
    eng = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    Session = sessionmaker(bind=eng)
    return Session()


def _add_job(db_sess):
    j = Job(external_id="J1", title="Role")
    db_sess.add(j)
    db_sess.commit()
    db_sess.refresh(j)
    return j


def test_pipeline_counts_include_all_applicants_not_preview_window(db_sess):
    """
    Regression: dashboard pipeline totals must not follow the capped recent-applicant query.
    """
    job = _add_job(db_sess)
    t_recent = datetime.utcnow()
    t_old = t_recent - timedelta(days=1)

    for i in range(2):
        c = Candidate(external_id=f"c{i}", full_name=f"N{i}", created_at=t_recent)
        db_sess.add(c)
        db_sess.flush()
        db_sess.add(
            JobApplicant(
                job_id=job.id,
                candidate_id=c.id,
                status="new",
                updated_at=t_recent + timedelta(seconds=i),
            )
        )

    c_hired = Candidate(external_id="hired1", full_name="Hired Person", created_at=t_recent)
    db_sess.add(c_hired)
    db_sess.flush()
    db_sess.add(
        JobApplicant(
            job_id=job.id,
            candidate_id=c_hired.id,
            status="hired",
            updated_at=t_old,
        )
    )
    db_sess.commit()

    data = dw.build_dashboard_widgets(db_sess)
    pipe = {row["key"]: row["count"] for row in data["pipeline"]}
    assert pipe["new"] == 2
    assert pipe["hired"] == 1


def test_profile_status_without_job_applicant_row_counts_and_shows_avatar(db_sess):
    """Candidates edited only on the profile (no job_applicants) must appear on the tracker."""
    _add_job(db_sess)
    c = Candidate(
        external_id="solo",
        full_name="Solo Hire",
        status="hired",
        created_at=datetime.utcnow(),
    )
    db_sess.add(c)
    db_sess.commit()

    data = dw.build_dashboard_widgets(db_sess)
    pipe = {row["key"]: row for row in data["pipeline"]}
    assert pipe["hired"]["count"] >= 1
    assert any(p["external_id"] == "solo" for p in pipe["hired"]["people"])
