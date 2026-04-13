"""
PII stripping for resume/JD text before training and inference.
Ensures PII is not used as features and reduces privacy/fairness risk.

Bias / fairness notes (FYP):
- Emails, phones, and URLs are removed so the model is less likely to latch onto
  contact strings or social profiles as spurious shortcuts.
- We do **not** aggressively strip pronouns or narrative gender markers from free
  text, because that can mangle grammar and job-description wording; mitigating
  demographic bias should combine **structured fields** (skills, experience),
  **diverse training data**, and **human review**—not regex-only “fairness.”
- For stronger controls, pair this module with rule-based hiring workflows and
  periodic audits of false positives/negatives by demographic slice (when labels exist).
"""
from __future__ import annotations

import re
from typing import Optional

# Placeholders (no semantic signal)
REPL_EMAIL = " [EMAIL] "
REPL_PHONE = " [PHONE] "
REPL_URL = " [URL] "
REPL_NAME_CANDIDATE = " [NAME] "  # optional: strip "Name" lines at top of resume

# Common patterns (conservative to avoid breaking technical text)
RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)
RE_PHONE = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{2,4}[\s.-]?\d{2,4}(?:[\s.-]?\d{2,4})?\b"
)
RE_URL = re.compile(
    r"https?://[^\s<>\"']+|www\.[^\s<>\"']+|linkedin\.com/[^\s<>\"']+|github\.com/[^\s<>\"']+",
    re.IGNORECASE
)


def strip_email(text: str) -> str:
    if not text:
        return text
    return RE_EMAIL.sub(REPL_EMAIL.strip(), text)


def strip_phone(text: str) -> str:
    if not text:
        return text
    return RE_PHONE.sub(REPL_PHONE.strip(), text)


def strip_url(text: str) -> str:
    if not text:
        return text
    return RE_URL.sub(REPL_URL.strip(), text)


def strip_pii(
    text: str,
    strip_emails: bool = True,
    strip_phones: bool = True,
    strip_urls: bool = True,
) -> str:
    """
    Replace PII in text with placeholders. Normalizes whitespace after replacement.
    """
    if not isinstance(text, str) or not text.strip():
        return text or ""

    out = text
    if strip_emails:
        out = RE_EMAIL.sub(REPL_EMAIL, out)
    if strip_phones:
        out = RE_PHONE.sub(REPL_PHONE, out)
    if strip_urls:
        out = RE_URL.sub(REPL_URL, out)

    # Collapse multiple spaces/newlines from replacements
    out = re.sub(r"\s+", " ", out).strip()
    return out


def contains_pii(text: str) -> bool:
    """Quick check if text likely contains PII (for safety checks)."""
    if not text:
        return False
    return bool(RE_EMAIL.search(text) or RE_PHONE.search(text) or RE_URL.search(text))
