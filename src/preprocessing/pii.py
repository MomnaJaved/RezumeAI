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


def strip_pii_keep_newlines(
    text: str,
    strip_emails: bool = True,
    strip_phones: bool = True,
    strip_urls: bool = True,
) -> str:
    """
    Same replacements as strip_pii, but preserve line breaks so line-based resume
    parsers (education, certifications) still see section structure.
    """
    if not isinstance(text, str) or not text.strip():
        return text or ""

    out = text.replace("\r\n", "\n").replace("\r", "\n")
    if strip_emails:
        out = RE_EMAIL.sub(REPL_EMAIL, out)
    if strip_phones:
        out = RE_PHONE.sub(REPL_PHONE, out)
    if strip_urls:
        out = RE_URL.sub(REPL_URL, out)

    lines = []
    for line in out.split("\n"):
        lines.append(re.sub(r"[ \t]+", " ", line).strip())
    return "\n".join(lines).strip()


def contains_pii(text: str) -> bool:
    """Quick check if text likely contains PII (for safety checks)."""
    if not text:
        return False
    return bool(RE_EMAIL.search(text) or RE_PHONE.search(text) or RE_URL.search(text))


_RE_SPACED_AT = re.compile(r"([A-Za-z0-9._%+-])\s+@\s+([A-Za-z0-9._%+-])")
_RE_SKIP_EMAIL = re.compile(
    r"noreply|no[-_]?reply|donotreply|mailer-daemon|notifications?@|bounce|@example\.(com|org)\b",
    re.IGNORECASE,
)
_RE_MAILTO = re.compile(r"mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.IGNORECASE)
_RE_LABELED_EMAIL = re.compile(
    r"(?:^|[\n\r;|])(?:e[-_]?mail|e\s*mail|contact)\s*[:=#]\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    re.IGNORECASE | re.MULTILINE,
)
_RE_AT_TOKEN = re.compile(
    r"\b([A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9][A-Za-z0-9.-]{0,120}\.[A-Za-z]{2,24})\b"
)


def normalize_text_for_email_scan(text: str) -> str:
    """Undo common PDF/obfuscation patterns so RE_EMAIL can match."""
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "")
    # Obfuscated "@": [at], (at) — do not replace bare English " at " (e.g. "Reach me at user@…").
    t = re.sub(r"\[\s*at\s*\]|\(\s*at\s*\)", "@", t, flags=re.IGNORECASE)
    t = re.sub(r"\(?\s*\[?\s*dot\s*\]?\s*\)?", ".", t, flags=re.IGNORECASE)
    t = _RE_SPACED_AT.sub(r"\1@\2", t)
    return t


def extract_primary_email(text: str, *, max_len: int = 320) -> str:
    """
    Best-effort email for the contact_email field (stored in DB; not stripped from structured field).
    Prefers matches in the first ~6k chars (header/contact area), then scans the rest.
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    def addr_ok(addr: str) -> bool:
        a = addr.strip().lower()
        if len(a) < 5 or len(a) > max_len:
            return False
        if _RE_SKIP_EMAIL.search(a):
            return False
        return bool(_RE_AT_TOKEN.fullmatch(a)) or bool(RE_EMAIL.fullmatch(a))

    def pick(norm: str) -> str:
        for rx in (_RE_LABELED_EMAIL, _RE_MAILTO):
            for m in rx.finditer(norm):
                addr = m.group(1).strip().lower()
                if addr_ok(addr):
                    return addr[:max_len]
        for m in RE_EMAIL.finditer(norm):
            addr = m.group(0).strip().lower()
            if addr_ok(addr):
                return addr[:max_len]
        for m in _RE_AT_TOKEN.finditer(norm):
            addr = m.group(1).strip().lower()
            if addr_ok(addr):
                return addr[:max_len]
        return ""

    head = text[:6000]
    got = pick(normalize_text_for_email_scan(head))
    if got:
        return got
    return pick(normalize_text_for_email_scan(text))
