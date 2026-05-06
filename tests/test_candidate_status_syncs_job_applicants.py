from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.database import Base
from api.models import Candidate, Job, JobApplicant
from api.routers.candidates import patch_candidate
from api.schemas import CandidateUpdate


@pytest.fixture
def db_sess(tmp_path):
    db_path = tmp_path / "sync.db"
    eng = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    Session = sessionmaker(bind=eng)
    return Session()


def test_patch_candidate_status_propagates_to_all_job_applicants(db_sess):
    j1 = Job(external_id="J1", title="Role A")
    j2 = Job(external_id="J2", title="Role B")
    db_sess.add_all([j1, j2])
    c = Candidate(external_id="c1", full_name="Pat", status="new", created_at=datetime.utcnow())
    db_sess.add(c)
    db_sess.commit()
    db_sess.refresh(j1)
    db_sess.refresh(j2)
    db_sess.refresh(c)
    now = datetime.utcnow()
    db_sess.add_all(
        [
            JobApplicant(job_id=j1.id, candidate_id=c.id, status="new", updated_at=now),
            JobApplicant(job_id=j2.id, candidate_id=c.id, status="screened", updated_at=now),
        ]
    )
    db_sess.commit()

    patch_candidate(c.id, CandidateUpdate(status="hired"), db_sess, None)

    rows = db_sess.query(JobApplicant).filter(JobApplicant.candidate_id == c.id).all()
    assert len(rows) == 2
    assert {r.status for r in rows} == {"hired"}
    db_sess.refresh(c)
    assert c.status == "hired"


def test_patch_candidate_persists_skills_and_certifications(db_sess):
    c = Candidate(
        external_id="c2",
        full_name="Sam",
        skills="old",
        certifications="old cert",
        education_lines="",
        status="new",
        created_at=datetime.utcnow(),
    )
    db_sess.add(c)
    db_sess.commit()
    db_sess.refresh(c)

    patch_candidate(
        c.id,
        CandidateUpdate(
            skills="Python, SQL",
            certifications="AWS SAA | PMP",
            education_lines="Uni | BS",
        ),
        db_sess,
        None,
    )
    db_sess.refresh(c)
    assert c.skills == "Python, SQL"
    assert c.certifications == "AWS SAA | PMP"
    assert c.education_lines == "Uni | BS"


def test_patch_candidate_null_strings_coerce_to_empty(db_sess):
    c = Candidate(
        external_id="c3",
        full_name="T",
        skills="x",
        certifications="y",
        created_at=datetime.utcnow(),
    )
    db_sess.add(c)
    db_sess.commit()
    db_sess.refresh(c)
    patch_candidate(c.id, CandidateUpdate(skills=None, certifications=None), db_sess, None)
    db_sess.refresh(c)
    assert c.skills == ""
    assert c.certifications == ""
