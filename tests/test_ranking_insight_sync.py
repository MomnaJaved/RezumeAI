from __future__ import annotations

from uuid import uuid4

from api.services.ranking_insight_sync import _filter_rows_for_insight, _insight_cache_key


def test_filter_rows_keeps_only_shortlisted_when_shortlist_nonempty():
    id1, id2 = uuid4(), uuid4()
    jr1 = type("JR", (), {"cross_encoder_score": 0.5})()
    jr2 = type("JR", (), {"cross_encoder_score": 0.9})()
    c1 = type("C", (), {"id": id1, "external_id": "A"})()
    c2 = type("C", (), {"id": id2, "external_id": "B"})()
    rows = [(jr1, c1), (jr2, c2)]
    out = _filter_rows_for_insight(rows, {id2})
    assert len(out) == 1 and out[0][1].external_id == "B"
    assert out[0][0].cross_encoder_score == 0.9


def test_filter_rows_keeps_all_when_no_shortlist_rows():
    id1, id2 = uuid4(), uuid4()
    jr1 = type("JR", (), {"cross_encoder_score": 0.3})()
    jr2 = type("JR", (), {"cross_encoder_score": 0.9})()
    c1 = type("C", (), {"id": id1, "external_id": "A"})()
    c2 = type("C", (), {"id": id2, "external_id": "B"})()
    rows = [(jr1, c1), (jr2, c2)]
    out = _filter_rows_for_insight(rows, set())
    assert len(out) == 2
    assert out[0][1].external_id == "B"  # sorted by score desc


def test_insight_cache_key_changes_when_shortlist_membership_changes():
    from datetime import datetime, timezone

    id1 = uuid4()
    jr = type("JR", (), {"cross_encoder_score": 0.8})()
    c = type("C", (), {"id": id1, "external_id": "X"})()
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    k1 = _insight_cache_key([(jr, c)], ts)
    c2 = type("C", (), {"id": uuid4(), "external_id": "Y"})()
    k2 = _insight_cache_key([(jr, c), (jr, c2)], ts)
    assert k1 != k2
