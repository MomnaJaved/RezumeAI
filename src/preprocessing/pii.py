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


def _repair_ocr_missing_at_before_common_hosts(t: str) -> str:
    """
    OCR on low-contrast sidebars often drops '@' or spaces the TLD (e.g. 'user gmail com').
    Insert a canonical address so RE_EMAIL / _RE_AT_TOKEN can match.
    Handles spaced locals like 'shahid maheen 22 gmail com' (one line).
    """
    if not t:
        return t
    # Host tokens allow OCR letter-spacing (e.g. "g mail" → gmail).
    hosts = (
        (r"g\s*mail", "gmail.com"),
        (r"o\s*u\s*t\s*l\s*o\s*o\s*k", "outlook.com"),
        (r"h\s*o\s*t\s*m\s*a\s*i\s*l", "hotmail.com"),
        (r"y\s*a\s*h\s*o\s*o", "yahoo.com"),
        (r"p\s*r\s*o\s*t\s*o\s*n\s*m\s*a\s*i\s*l", "protonmail.com"),
        (r"i\s*c\s*l\s*o\s*u\s*d", "icloud.com"),
    )
    out: list[str] = []
    for line in t.splitlines():
        s = line
        for host_pat, fqdn in hosts:
            # Spaced TLD: g mail c o m / gmail com
            pat = re.compile(
                rf"(?i)(?P<local>[a-z0-9](?:[a-z0-9._%+-]|\s+[a-z0-9._%+-]){{0,52}})\s+{host_pat}\s*(?:\.|\s+)+c\s*o\s*m\b",
            )
            s = pat.sub(
                lambda m, fq=fqdn: re.sub(r"\s+", "", m.group("local").strip()) + "@" + fq,
                s,
            )
            pat2 = re.compile(
                rf"(?i)(?P<local>[a-z0-9](?:[a-z0-9._%+-]|\s+[a-z0-9._%+-]){{0,52}})\s+{host_pat}\s*\.\s*com\b",
            )
            s = pat2.sub(
                lambda m, fq=fqdn: re.sub(r"\s+", "", m.group("local").strip()) + "@" + fq,
                s,
            )
        out.append(s)
    return "\n".join(out)


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
    # OCR: spaces inside local-part or between domain labels (jane . doe @ g mail . com)
    for _ in range(8):
        t2 = t
        t2 = re.sub(r"([\w.%+-])\s+([\w.%+-])\s*@", r"\1\2@", t2)
        t2 = re.sub(r"@\s*([\w.-])\s+([\w.-])", r"@\1\2", t2)
        t2 = re.sub(r"([\w.%+-])\s+\.\s+([\w.%+-])", r"\1.\2", t2)
        t2 = re.sub(r"(\.[a-z]{2,})\s+\.", r"\1.", t2, flags=re.IGNORECASE)
        if t2 == t:
            break
        t = t2
    t = _repair_ocr_missing_at_before_common_hosts(t)
    t = _repair_local_stuck_to_public_domain(t)
    return t


def _repair_local_stuck_to_public_domain(t: str) -> str:
    """
    OCR often drops '@' so 'shahidmaheen20' and 'gmail.com' become one token or 'shahidmaheen20gmail.com'.
    Insert @ only when the local part ends with digits (common personal addresses) to limit false positives.
    """
    if not t:
        return t
    doms = (
        (r"gmail\.com", "gmail.com"),
        (r"yahoo\.com", "yahoo.com"),
        (r"hotmail\.com", "hotmail.com"),
        (r"outlook\.com", "outlook.com"),
        (r"protonmail\.com", "protonmail.com"),
        (r"icloud\.com", "icloud.com"),
    )
    for dom_re, dom_lit in doms:
        t = re.sub(
            rf"(?i)(?<![@\w.])([a-z0-9][a-z0-9._%+-]{{3,40}}\d)({dom_re})\b",
            rf"\1@{dom_lit}",
            t,
        )
    # Academic / regional TLDs (common on PK résumés; OCR often drops ``@``).
    for dom_lit, dom_re in (
        ("edu.pk", r"edu\.pk"),
        ("com.pk", r"com\.pk"),
        ("ac.uk", r"ac\.uk"),
    ):
        t = re.sub(
            rf"(?i)(?<![@\w.])([a-z0-9][a-z0-9._%+-]{{3,52}})({dom_re})\b",
            rf"\1@{dom_lit}",
            t,
        )
    return t


def _pick_email_collapsed_lines(norm: str, addr_ok) -> str:
    """OCR often breaks tokens with spaces; strip whitespace per line and scan for addresses."""
    for line in norm.splitlines():
        collapsed = re.sub(r"\s+", "", line)
        if len(collapsed) < 6 or "@" not in collapsed:
            continue
        for m in RE_EMAIL.finditer(collapsed):
            addr = m.group(0).strip().lower()
            if addr_ok(addr):
                return addr
        for m in _RE_AT_TOKEN.finditer(collapsed):
            addr = m.group(1).strip().lower()
            if addr_ok(addr):
                return addr
    return ""


def _header_email_blob_for_ocr(norm_head: str) -> str:
    """
    Collapse only the email-looking lines (from the first ``@`` / major host hint),
    so the candidate's name on earlier lines is not glued into the local-part.
    """
    lines = [ln.strip() for ln in norm_head.splitlines() if ln.strip()][:40]
    start: int | None = None
    for i, ln in enumerate(lines):
        if "@" in ln or re.search(
            r"\b(gmail|yahoo|hotmail|outlook|protonmail|icloud|edu\.pk|ac\.uk)\b", ln, re.IGNORECASE
        ):
            start = i
            break
    if start is None:
        return ""
    chunk = lines[start : start + 5]
    return "".join(re.sub(r"\s+", "", x) for x in chunk)


def _pick_email_from_collapsed_text(flat: str, addr_ok) -> str:
    """Scan text with all whitespace removed (fixes ``user@\\n  gmail.com`` from OCR)."""
    if not flat or "@" not in flat:
        return ""
    for m in RE_EMAIL.finditer(flat):
        addr = m.group(0).strip().lower()
        if addr_ok(addr):
            return addr
    for m in _RE_AT_TOKEN.finditer(flat):
        addr = m.group(1).strip().lower()
        if addr_ok(addr):
            return addr
    return ""


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
        loose = _pick_email_collapsed_lines(norm, addr_ok)
        if loose:
            return loose[:max_len]
        return ""

    # Merged multi-pass OCR can be long; keep more of the header/contact area.
    head = text[:12000]
    norm_head = normalize_text_for_email_scan(head)
    got = pick(norm_head)
    if got:
        return got
    # OCR often breaks an address across lines; collapse helps only on the header (not whole CV),
    # otherwise names glue into the local-part and produce false matches.
    head_for_blob = norm_head
    m_cut = re.search(
        r"(?i)\n\s*(skills|technical\s+skills|experience|work\s+experience|education|projects|summary|objective)\b\s*:?",
        head_for_blob,
    )
    if m_cut:
        head_for_blob = head_for_blob[: m_cut.start()]
    flat = _header_email_blob_for_ocr(head_for_blob)
    got = _pick_email_from_collapsed_text(flat, addr_ok) if flat else ""
    if got:
        return got[:max_len]
    full_norm = normalize_text_for_email_scan(text)
    got = pick(full_norm)
    if got:
        return got
    blob_src = full_norm[:16000]
    m_cut2 = re.search(
        r"(?i)\n\s*(skills|technical\s+skills|experience|work\s+experience|education|projects|summary|objective)\b\s*:?",
        blob_src,
    )
    if m_cut2:
        blob_src = blob_src[: m_cut2.start()]
    flat2 = _header_email_blob_for_ocr(blob_src)
    got = _pick_email_from_collapsed_text(flat2, addr_ok) if flat2 else ""
    return got[:max_len] if got else ""
