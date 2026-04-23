"""
Optional spaCy-based NLP enrichment for résumés (NER + noun-phrase skill hints).

Install the English pipeline once::

    python -m spacy download en_core_web_sm

If the model is missing, all functions degrade gracefully (empty enrichment).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

from src.parsing.skill_mining import CORE_TOOLS, RE_PHRASES

_log = logging.getLogger("rezume.nlp")

_NLP = None
_YEAR_RANGE = re.compile(
    r"\b((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2}|present|current|now|till|to\s+date)\b",
    re.IGNORECASE,
)
_ROLEISH = re.compile(
    r"\b(engineer|developer|designer|analyst|architect|manager|lead|consultant|scientist|specialist)\b",
    re.IGNORECASE,
)


@dataclass
class ResumeNlpEnrichment:
    """Structured signals derived from a single spaCy pass."""

    person_names: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    skill_like_chunks: list[str] = field(default_factory=list)
    title_hint: str = ""
    years_hint_from_ranges: float | None = None
    spacy_loaded: bool = False
    note: str = ""


def _get_nlp():
    global _NLP
    if _NLP is False:
        return None
    if _NLP is not None:
        return _NLP
    try:
        import spacy

        _NLP = spacy.load("en_core_web_sm")
        return _NLP
    except Exception as e:
        _NLP = False
        _log.debug("spaCy English model unavailable: %s", e)
        return None


def _chunk_overlaps_any_span(
    chunk_start: int, chunk_end: int, spans: Iterable[tuple[int, int]]
) -> bool:
    for a, b in spans:
        if chunk_end > a and chunk_start < b:
            return True
    return False


def _years_from_year_ranges(text: str) -> float | None:
    """Coarse tenure from explicit 4-digit ranges (complements section-based estimators)."""
    from datetime import datetime

    now_y = datetime.now().year
    t = text[:8000]
    best = 0.0
    for m in _YEAR_RANGE.finditer(t):
        try:
            y1 = int(m.group(1))
        except (ValueError, IndexError, TypeError):
            continue
        g2 = (m.group(2) or "").strip().lower()
        if g2 in ("present", "current", "now", "till", "to date"):
            y2 = now_y
        else:
            try:
                y2 = int(g2)
            except ValueError:
                continue
        if y2 > y1 and (y2 - y1) <= 50:
            best = max(best, float(y2 - y1))
    return best if best > 0 else None


def _skill_like_chunk(text: str) -> bool:
    low = text.lower().strip()
    if len(low) < 2 or len(low) > 56:
        return False
    if RE_PHRASES.search(low):
        return True
    lemmas = low.replace(".js", "").split()
    for w in lemmas:
        wn = re.sub(r"[^a-z0-9\+\#]", "", w)
        if wn in CORE_TOOLS:
            return True
    if any(ch.isupper() for ch in text) and re.search(r"[A-Za-z].*[A-Za-z]", text):
        if not re.search(r"\b(the|and|for|with|from|this|that|have|has|was|were)\b", low):
            if re.search(r"\d", text) or "." in text or "/" in text or "+" in text:
                return True
    return False


def _title_hint_from_doc(doc) -> str:
    head = doc[: min(len(doc), 320)]
    best = ""
    for nc in head.noun_chunks:
        t = nc.text.strip()
        if 6 <= len(t) <= 72 and _ROLEISH.search(t):
            if len(t) > len(best):
                best = t
    return best.strip().lower()


def enrich_resume_text(text: str, *, max_chars: int = 12000) -> ResumeNlpEnrichment:
    """
    Run spaCy NER + noun chunks on a prefix of the résumé (cost control).

    Returns empty enrichment when spaCy or ``en_core_web_sm`` is missing.
    """
    raw = (text or "").strip()
    if len(raw) < 40:
        return ResumeNlpEnrichment(note="text_too_short")

    nlp = _get_nlp()
    if nlp is None:
        return ResumeNlpEnrichment(note="spacy_or_model_missing")

    snippet = raw[:max_chars]
    doc = nlp(snippet)

    person_spans: list[tuple[int, int]] = []
    persons: list[str] = []
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            cleaned = " ".join(ent.text.split())
            if 3 <= len(cleaned) <= 60 and cleaned.count(" ") <= 4:
                persons.append(cleaned)
                person_spans.append((ent.start_char, ent.end_char))
        elif ent.label_ == "ORG":
            o = " ".join(ent.text.split())
            if 4 <= len(o) <= 80:
                pass  # collected below

    orgs = []
    for ent in doc.ents:
        if ent.label_ == "ORG":
            o = " ".join(ent.text.split())
            if 4 <= len(o) <= 80:
                orgs.append(o)

    skills: list[str] = []
    seen: set[str] = set()
    for nc in doc.noun_chunks:
        if _chunk_overlaps_any_span(nc.start_char, nc.end_char, person_spans):
            continue
        t = nc.text.strip()
        if not _skill_like_chunk(t):
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        skills.append(t)
        if len(skills) >= 40:
            break

    y_hint = _years_from_year_ranges(raw)
    th = _title_hint_from_doc(doc)

    return ResumeNlpEnrichment(
        person_names=persons[:6],
        organizations=orgs[:12],
        skill_like_chunks=skills,
        title_hint=th,
        years_hint_from_ranges=y_hint,
        spacy_loaded=True,
        note="ok",
    )


def merge_skill_candidates(
    keyword_skills: list[str],
    nlp: ResumeNlpEnrichment,
    *,
    max_total: int = 80,
) -> list[str]:
    """Union keyword-mined skills with spaCy noun-chunk hints, preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for s in keyword_skills:
        k = (s or "").strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append((s or "").strip())
    for s in nlp.skill_like_chunks:
        k = s.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(s.strip())
        if len(out) >= max_total:
            break
    return out[:max_total]


def augment_years_experience(existing: float, nlp: ResumeNlpEnrichment) -> float:
    """Take the max of heuristic years and NLP range-derived hint."""
    try:
        base = float(existing)
    except (TypeError, ValueError):
        base = 0.0
    hint = nlp.years_hint_from_ranges
    if hint is None:
        return base
    try:
        h = float(hint)
    except (TypeError, ValueError):
        return base
    if h <= 0:
        return base
    merged = max(base, min(h, 45.0))
    return merged


def suggest_name_from_nlp(
    resolved_name: str,
    nlp: ResumeNlpEnrichment,
    *,
    max_tokens: int = 4,
) -> str:
    """
    If heuristics left the name blank, use the first plausible PERSON span
    from the header region (spaCy already ran on snippet).
    """
    if (resolved_name or "").strip():
        return resolved_name
    for p in nlp.person_names:
        parts = p.split()
        if 1 <= len(parts) <= max_tokens:
            if all(re.match(r"^[A-Za-z][A-Za-z\-'.]*$", x) for x in parts):
                return p
    return resolved_name
