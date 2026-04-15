"""
Extract a person's name from the top of a resume (before strip_pii collapses layout).

Handles common patterns: labeled "Name:", header lines with | or bullets separating name from title,
and initials (J. K. Rowling). Avoids picking job titles when possible.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

_log = logging.getLogger("rezume.parsing")

# Display default when resume text + email do not yield a confident person name.
UNKNOWN_CANDIDATE = "Unknown Candidate"

_SKIP_EMAIL_LOCAL_PREFIXES = frozenset(
    {
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "mailer-daemon",
        "postmaster",
        "bounce",
        "support",
        "help",
        "helpdesk",
        "hello",
        "team",
        "admin",
        "info",
        "contact",
        "sales",
        "careers",
        "jobs",
        "hr",
        "recruiting",
        "newsletter",
        "notifications",
        "notification",
    }
)

# Split header lines: name | title | contact — PDFs often glue these together.
RE_HEADER_SPLIT = re.compile(r"[|•·\u2022]+|\t+| {3,}")
RE_NAME_LABEL = re.compile(
    r"^\s*(?:full\s*name|name|candidate(?:\s+name)?)\s*[:;]\s*(.+?)\s*$",
    re.IGNORECASE,
)
RE_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+|linkedin\.com|github\.com|http", re.IGNORECASE)
RE_PHONEISH = re.compile(r"\b\+?\d[\d\s().-]{7,}\d\b")
RE_CREDENTIAL_HINT = re.compile(
    r"\b(certified|certification|certifications|certificate|certificates|credential|credentials|"
    r"license|licence|licensed|licenced|badge|badges)\b",
    re.IGNORECASE,
)

# Same role lexicon as title_extractor (avoid returning a job title as the name).
ROLE_KEYWORDS = {
    "engineer",
    "developer",
    "designer",
    "analyst",
    "scientist",
    "manager",
    "specialist",
    "consultant",
    "officer",
    "executive",
    "lead",
    "intern",
    "associate",
    "architect",
    "tester",
    "qa",
    "sqa",
    "director",
    "coordinator",
    "administrator",
    "programmer",
}

RE_TITLE_PHRASE = re.compile(
    r"\b("
    r"(?:senior|sr\.?|junior|jr\.?|lead|principal|assistant)?\s*"
    r"(?:software|backend|frontend|full\s*stack|fullstack|web|mobile|android|ios|data|ml|ai|qa|sqa|ui/ux|ux/ui|ui|ux)?\s*"
    r"(?:engineer|developer|designer|analyst|scientist|manager|tester|intern|architect)"
    r")\b",
    re.IGNORECASE,
)

# "Finance Analyst", "Business Analyst", etc. — two-word job titles often mistaken for names.
RE_DOMAIN_ROLE_TITLE = re.compile(
    r"\b("
    r"finance|financial|business|data|product|marketing|credit|investment|tax|budget|revenue|operations|"
    r"information|technical|staff|project|program|account|sales|customer|supply|quality|risk|policy|hr|it"
    r")\s+(analyst|associate|consultant|specialist|coordinator|administrator)\b",
    re.IGNORECASE,
)

# Lines that are clearly not a name row.
RE_BAD_LINE_HINT = re.compile(
    r"\b(resume|curriculum vitae|\bcv\b|page\s+\d|confidential|table of contents|"
    r"professional\s+summary|summary|objective|about\s+me)\b",
    re.IGNORECASE,
)

# Honorifics to strip from labeled or chunk values.
RE_HONORIFIC = re.compile(
    r"^\s*(?:mr\.?|mrs\.?|ms\.?|miss|dr\.?|prof\.?|eng\.?|engr\.?)\s+",
    re.IGNORECASE,
)

# Skills, org suffixes, and course topics that match "two capitalized words" but are not people.
_PHRASE_NOT_A_NAME = frozenset(
    {
        "time management",
        "project management",
        "stress management",
        "change management",
        "risk management",
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "data science",
        "computer science",
        "information technology",
        "business analysis",
        "business analyst",
        "quality assurance",
        "customer service",
        "human resources",
        "supply chain",
        "public relations",
        "financial analysis",
        "operations management",
        "product management",
        "sales management",
        "aws certified",
        "azure certified",
        "google certified",
    }
)

_TOKEN_NOT_A_NAME = frozenset(
    {
        "software",
        "technologies",
        "technology",
        "solutions",
        "systems",
        "consulting",
        "services",
        "management",
        "intelligence",
        "learning",
        "science",
        "sciences",
        "analytics",
        "automation",
        "development",
        "engineering",
        "database",
        "databases",
        "security",
        "networking",
        "network",
        "application",
        "applications",
        "enterprise",
        "digital",
        "cloud",
        "data",
        "machine",
        "artificial",
        "professional",
        "technical",
        "certification",
        "certifications",
        "certified",
        "certificate",
        "certificates",
        "credential",
        "credentials",
        "license",
        "licence",
        "licensed",
        "licenced",
        "badge",
        "badges",
        "university",
        "college",
        "institute",
        "international",
        "corporation",
        "incorporated",
        "limited",
        "partners",
        "group",
        "laboratory",
        "laboratories",
        "labs",
        "pvt",
        "ltd",
        "llc",
        "inc",
        "corp",
        "plc",
        "global",
        "national",
        "regional",
        "marketing",
        "sales",
        "operations",
        "strategy",
        "research",
        "experience",
        "skills",
        "education",
        "summary",
        "objective",
        "profile",
        "programming",
        "framework",
        "frameworks",
        "testing",
        "assurance",
        "computer",
        "resource",
        "resources",
        "communications",
        "media",
        "financial",
        "accounting",
        "design",
        "designer",
        "architecture",
        "infrastructure",
        "devops",
        "agile",
        "scrum",
    }
)


def _looks_like_skill_topic_or_company(name: str) -> bool:
    """Reject 'Contour Software', 'Time management', 'Artificial Intelligence', etc."""
    low = re.sub(r"\s+", " ", (name or "").strip().lower())
    if not low:
        return True
    if low in _PHRASE_NOT_A_NAME:
        return True
    words = [w for w in re.findall(r"[a-z]+", low) if w]
    if not words:
        return True
    if any(w in _TOKEN_NOT_A_NAME for w in words):
        return True
    return False


def _word_token_ok(w: str) -> bool:
    w = w.strip()
    if not w or not any(c.isalpha() for c in w):
        return False
    # Single-letter initial, optional period (J. or J)
    if len(w) <= 2 and w[0].isalpha():
        return len(w) == 1 or w[1] == "."
    for c in w:
        if not (c.isalpha() or c in "-'’."):
            return False
    if w.count(".") > 1:
        return False
    return True


def _normalize_name_parts(raw: str) -> str:
    s = RE_HONORIFIC.sub("", (raw or "").strip())
    # Handle "LAST, FIRST [M.]" common in some templates
    if "," in s and s.count(",") == 1:
        a, b = [x.strip() for x in s.split(",", 1)]
        if a and b:
            s = f"{b} {a}"
    s = re.sub(r"\s*\([^)]{0,80}\)\s*$", "", s).strip()
    s = re.sub(r"[•|·]+$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    parts = s.split()
    if not parts:
        return ""
    if not (2 <= len(parts) <= 6):
        return ""
    for p in parts:
        if not _word_token_ok(p):
            return ""
    out = " ".join(parts)

    # Reject short ALLCAPS tokens that usually indicate skills/keywords (AWS, SQL, API),
    # but only when the overall candidate isn't fully uppercased (common in resume headers).
    # This avoids false positives like "Python, AWS" → "AWS Python" while still allowing
    # "ALI JANJUA".
    any_lower = any(c.islower() for c in out if c.isalpha())
    if any_lower:
        for p in parts:
            letters = [c for c in p if c.isalpha()]
            if letters and all(c.isupper() for c in letters) and 2 <= len(letters) <= 4 and "." not in p:
                return ""

    # If everything is ALLCAPS, title-case it for display.
    letters = [c for c in out if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        out = " ".join(w if (len(w) <= 2 and w.endswith(".")) else (w[:1].upper() + w[1:].lower()) for w in out.split())
    return out


def _looks_like_job_title(s: str) -> bool:
    low = s.lower().strip()
    if not low:
        return True
    if RE_DOMAIN_ROLE_TITLE.search(low):
        return True
    if RE_TITLE_PHRASE.search(low):
        m = RE_TITLE_PHRASE.search(low)
        if m and len(m.group(0)) >= min(len(low) * 0.65, len(low) - 2):
            return True
    words = re.findall(r"[a-z]+", low)
    role_hits = sum(1 for w in words if w in ROLE_KEYWORDS)
    if role_hits >= 2:
        return True
    if role_hits >= 1 and len(words) >= 4:
        return True
    return False


_TAIL_FILENAME_WORDS = frozenset(
    {
        "resume",
        "cv",
        "curriculum",
        "final",
        "draft",
        "updated",
        "new",
        "v1",
        "v2",
        "v3",
        "pdf",
        "docx",
        "doc",
        "txt",
        "untitled",
        "document",
        "file",
        "profile",
        "copy",
        "sample",
        "samples",
        "test",
        "testing",
        "example",
    }
)


def guess_name_from_filename_stem(stem: str) -> str:
    """
    If the file stem looks like 'First_Last' or 'Jane Doe' (not 'Finance_Analyst_Resume'), return a display name.
    Otherwise return "" so callers can fall back to a neutral label.
    """
    stem = (stem or "").strip()
    if not stem or len(stem) > 56:
        return ""
    low_all = stem.lower()
    # If the stem is primarily a resume/document label, don't use it as a name.
    if re.search(r"\b(resume|cv|curriculum|résumé)\b", low_all) or re.search(
        r"\b(linkedin|profile|untitled|document|file)\b", low_all
    ):
        return ""
    if re.match(r"^[\d\s._-]+$", low_all):
        return ""

    raw = re.sub(r"[_-]+", " ", stem)
    parts = [p for p in raw.split() if p]
    if parts and parts[0].isdigit():
        return ""
    while parts and parts[-1].lower().rstrip("0123456789.") in _TAIL_FILENAME_WORDS:
        parts.pop()
    # Require at least two remaining words; a single leftover like "sample" is not a person's name.
    if len(parts) < 2:
        return ""
    cand = " ".join(parts)
    if _looks_like_job_title(cand) or _looks_like_skill_topic_or_company(cand):
        return ""
    if RE_CREDENTIAL_HINT.search(cand):
        return ""
    val = _normalize_name_parts(cand)
    if val and not _looks_like_job_title(val):
        return val
    return ""


def extract_name_from_raw(raw_text: str, *, max_lines: int = 40) -> str:
    """
    Return best-effort full name, or "" if none found.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return ""

    t = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # Stored raw_text is often PII-stripped with newlines collapsed to spaces; pipe-separated
    # headers ("Name | Title | …") then become one long line — split those back out.
    if t.count("\n") < 4 and "|" in t:
        t = re.sub(r"\s*\|\s*", "\n", t, count=24)

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()][:max_lines]

    def ok_candidate(val: str) -> bool:
        if not val:
            return False
        if val.strip().lower() in ("candidate", "unknown candidate", "unknown"):
            return False
        if RE_CREDENTIAL_HINT.search(val):
            return False
        return (not _looks_like_job_title(val)) and (not _looks_like_skill_topic_or_company(val))

    # Collect candidates with a score, then pick best above threshold.
    found: list[tuple[int, str]] = []

    # 1) Explicit labels (multilingual "Name:" common)
    for i, ln in enumerate(lines[:35]):
        m = RE_NAME_LABEL.match(ln)
        if not m:
            continue
        val = _normalize_name_parts(m.group(1).split("|")[0].strip())
        if ok_candidate(val):
            # Labeled names are high-confidence.
            found.append((100 - i, val))

    # 2) First plausible segment per line (split headers on | • tabs).
    # Do not drop the whole line just because one chunk has a phone/email.
    for i, ln in enumerate(lines[:28]):
        if RE_BAD_LINE_HINT.search(ln):
            continue

        line_has_contact = bool(RE_EMAIL.search(ln) or RE_PHONEISH.search(ln))
        chunks = [c.strip() for c in RE_HEADER_SPLIT.split(ln) if c.strip()] or [ln]
        for j, ch in enumerate(chunks):
            ch = ch.strip()
            if not ch or len(ch) > 70:
                continue
            if RE_EMAIL.search(ch) or RE_PHONEISH.search(ch):
                continue
            val = _normalize_name_parts(ch)
            if not ok_candidate(val):
                continue
            score = 80 - i * 2
            # Names on the same line as email/phone are usually in the header.
            if line_has_contact:
                score += 12
            # Earlier chunks on a header line are more likely name/title; keep but score slightly higher.
            score += max(0, 6 - j * 2)
            found.append((score, val))

    # 3) Legacy: whole line is only letters/spaces/hyphen/apostrophe (old heuristic, slightly wider)
    bad_words = ("resume", "curriculum vitae", "cv", "contact", "profile", "summary", "objective")
    for i, ln in enumerate(lines[:15]):
        low = ln.lower()
        if any(b in low for b in bad_words):
            continue
        if RE_EMAIL.search(ln) or "|" in ln or "\t" in ln:
            continue
        if 3 <= len(ln) <= 70 and all((c.isalpha() or c.isspace() or c in "-'") for c in ln):
            parts = [p for p in ln.replace("-", " ").split() if p]
            if 1 < len(parts) <= 5:
                cand = " ".join(parts)
                val = _normalize_name_parts(cand)
                if ok_candidate(val):
                    found.append((40 - i, val))

    if not found:
        return ""

    # Choose best-scoring unique candidate. Require a minimum confidence to avoid false positives.
    found.sort(key=lambda t: (-t[0], t[1]))
    best_score, best = found[0]
    if best_score < 45:
        return ""
    return best


def extract_name_from_email(email: str) -> str:
    """
    Derive a display name from an email local-part when it looks like firstname.lastname
    (e.g. ahmad.ali@gmail.com -> Ahmad Ali). Conservative: requires two+ alphabetic tokens.
    """
    e = (email or "").strip().lower()
    if "@" not in e:
        return ""
    local = e.split("@", 1)[0].strip()
    if "+" in local:
        local = local.split("+", 1)[0].strip()
    if not local or len(local) > 64:
        return ""
    if local in _SKIP_EMAIL_LOCAL_PREFIXES:
        return ""
    tokens = [t for t in re.split(r"[._-]+", local) if t]
    cleaned: list[str] = []
    for t in tokens:
        t = re.sub(r"\d+$", "", t)
        if len(t) < 2 or not t.isalpha():
            continue
        cleaned.append(t)
    if len(cleaned) < 2:
        return ""
    cleaned = cleaned[:4]
    out = " ".join(x[:1].upper() + x[1:].lower() for x in cleaned)
    low = out.lower()
    if _looks_like_job_title(out) or _looks_like_skill_topic_or_company(low):
        return ""
    if RE_CREDENTIAL_HINT.search(out):
        return ""
    return out


def resolve_candidate_full_name(raw_text: str, contact_email: Optional[str]) -> tuple[str, str]:
    """
    Resolve stored candidate full_name: resume header first, then email local-part, else UNKNOWN_CANDIDATE.
    Returns (name, source) where source is one of: resume, email, unknown.
    """
    guessed = extract_name_from_raw(raw_text or "")
    if guessed and guessed.strip().lower() not in ("candidate", "unknown candidate", "unknown"):
        return guessed, "resume"
    em = (contact_email or "").strip()
    from_email = extract_name_from_email(em) if em else ""
    if from_email:
        _log.debug("name_from_email email=%s name=%s", em, from_email)
        return from_email, "email"
    _log.debug("name_unresolved email_present=%s", bool(em))
    return UNKNOWN_CANDIDATE, "unknown"
