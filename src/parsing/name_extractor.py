"""
Extract a person's name from the top of a resume (before strip_pii collapses layout).

Handles common patterns: labeled "Name:", header lines with | or bullets separating name from title,
and initials (J. K. Rowling). Avoids picking job titles when possible.
"""
from __future__ import annotations

import re

# Split header lines: name | title | contact — PDFs often glue these together.
RE_HEADER_SPLIT = re.compile(r"[|•·\u2022]+|\t+| {3,}")
RE_NAME_LABEL = re.compile(
    r"^\s*(?:full\s*name|name|candidate(?:\s+name)?)\s*[:;]\s*(.+?)\s*$",
    re.IGNORECASE,
)
RE_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+|linkedin\.com|github\.com|http", re.IGNORECASE)
RE_PHONEISH = re.compile(r"\b\+?\d[\d\s().-]{7,}\d\b")

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
    s = re.sub(r"\s*\([^)]{0,80}\)\s*$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    parts = s.split()
    if not parts:
        return ""
    if not (2 <= len(parts) <= 6):
        return ""
    for p in parts:
        if not _word_token_ok(p):
            return ""
    return " ".join(parts)


def _looks_like_job_title(s: str) -> bool:
    low = s.lower().strip()
    if not low:
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

    # 1) Explicit labels (multilingual "Name:" common)
    for ln in lines[:35]:
        m = RE_NAME_LABEL.match(ln)
        if m:
            val = _normalize_name_parts(m.group(1).split("|")[0].strip())
            if val and not _looks_like_job_title(val) and not _looks_like_skill_topic_or_company(val):
                return val

    # 2) First plausible segment per line (split headers on | • tabs).
    # Do not drop the whole line just because one chunk has a phone/email.
    for ln in lines[:28]:
        if RE_BAD_LINE_HINT.search(ln):
            continue

        chunks = [c.strip() for c in RE_HEADER_SPLIT.split(ln) if c.strip()] or [ln]
        for ch in chunks:
            ch = ch.strip()
            if not ch or len(ch) > 70:
                continue
            if RE_EMAIL.search(ch) or RE_PHONEISH.search(ch):
                continue
            val = _normalize_name_parts(ch)
            if val and not _looks_like_job_title(val) and not _looks_like_skill_topic_or_company(val):
                return val

    # 3) Legacy: whole line is only letters/spaces/hyphen/apostrophe (old heuristic, slightly wider)
    bad_words = ("resume", "curriculum vitae", "cv", "contact", "profile", "summary", "objective")
    for ln in lines[:15]:
        low = ln.lower()
        if any(b in low for b in bad_words):
            continue
        if RE_EMAIL.search(ln) or "|" in ln or "\t" in ln:
            continue
        if 3 <= len(ln) <= 70 and all((c.isalpha() or c.isspace() or c in "-'") for c in ln):
            parts = [p for p in ln.replace("-", " ").split() if p]
            if 1 < len(parts) <= 5:
                cand = " ".join(parts)
                if not _looks_like_job_title(cand) and not _looks_like_skill_topic_or_company(cand):
                    return cand

    return ""
