from __future__ import annotations

from types import SimpleNamespace

from api.services.candidate_serialization import resolve_candidate_headline


def test_headline_replaces_stored_unknown_with_inference():
    c = SimpleNamespace(
        title="unknown",
        skills="react, node.js, postgresql",
        years_experience=2.0,
        role_label="",
        raw_text="",
    )
    h = resolve_candidate_headline(c)  # type: ignore[arg-type]
    assert h.strip()
    assert h.lower() != "unknown"


def test_headline_when_stored_title_polishes_empty():
    c = SimpleNamespace(
        title=" | ",
        skills="python, sql",
        years_experience=1.0,
        role_label="data",
        raw_text="",
    )
    h = resolve_candidate_headline(c)  # type: ignore[arg-type]
    assert h.strip()
