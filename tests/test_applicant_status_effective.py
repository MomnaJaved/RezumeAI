from __future__ import annotations

from datetime import datetime, timedelta

from api.services.applicant_status_effective import (
    applicant_tracker_counts,
    effective_applicant_status,
    effective_candidate_status,
)


def test_new_expires_to_screened():
    old = datetime.utcnow() - timedelta(days=10)
    assert effective_applicant_status("new", old) == "screened"
    assert effective_candidate_status("new", old) == "screened"


def test_new_stays_within_ttl():
    recent = datetime.utcnow() - timedelta(days=1)
    assert effective_applicant_status("new", recent) == "new"


def test_non_new_unchanged():
    assert effective_applicant_status("shortlisted", None) == "shortlisted"


def test_applicant_tracker_counts_merges_interviewing():
    recent = datetime.utcnow()
    pairs = [
        ("new", recent),
        ("interviewing", recent),
        ("rejected", recent),
    ]
    agg = applicant_tracker_counts(pairs)
    assert agg["total"] == 3
    assert agg["new"] == 1
    assert agg["interviewed"] == 1
    assert agg["rejected"] == 1
