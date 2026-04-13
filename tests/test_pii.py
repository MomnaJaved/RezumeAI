from __future__ import annotations

from src.preprocessing.pii import contains_pii, strip_pii


def test_strip_email():
    t = "Contact me at user@example.com today"
    out = strip_pii(t)
    assert "user@example.com" not in out
    assert "[EMAIL]" in out


def test_contains_pii():
    assert contains_pii("x@y.co")
    assert not contains_pii("no pii here")
