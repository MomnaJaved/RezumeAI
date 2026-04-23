"""
Post-extraction text preprocessing (digital PDFs, DOCX, and OCR).

Runs OCR-specific fixes from ``ocr_normalize`` plus light structural cleanup
(broken words, unicode noise) before NER / skill mining.
"""
from __future__ import annotations

import re

from src.parsing.ocr_normalize import normalize_resume_text_for_ocr

_RE_SOFT_HYPHEN_JOIN = re.compile(r"(\w)-\s*\n\s*(\w)")
_RE_MULTIPLE_BLANK = re.compile(r"\n{4,}")
_RE_NON_BREAKING_SPACE = re.compile(r"[\u00a0\u2007\u202f]")
_RE_STRAY_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _join_hyphenated_line_breaks(text: str) -> str:
    """Repair ``skill-\nning`` style breaks common in PDF/OCR."""
    t = text
    prev = None
    while prev != t:
        prev = t
        t = _RE_SOFT_HYPHEN_JOIN.sub(r"\1\2", t)
    return t


def _normalize_newlines_and_spaces(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = _RE_NON_BREAKING_SPACE.sub(" ", t)
    t = _RE_STRAY_CTRL.sub("", t)
    t = _RE_MULTIPLE_BLANK.sub("\n\n\n", t)
    return t.strip()


def preprocess_resume_text(text: str, *, apply_ocr_heuristics: bool = True) -> str:
    """
    Normalize résumé text after binary extraction (OCR or native PDF text).

    ``apply_ocr_heuristics``: letter-spaced names, mangled emails, etc. Safe for
    non-OCR text (patterns are mostly no-ops).
    """
    t = (text or "").strip()
    if not t:
        return ""
    t = _normalize_newlines_and_spaces(t)
    if apply_ocr_heuristics:
        t = normalize_resume_text_for_ocr(t)
    t = _join_hyphenated_line_breaks(t)
    t = _normalize_newlines_and_spaces(t)
    return t
