"""
Normalize candidate titles/roles for display: strip resume filler phrases, company tails,
pipe-separated name/company noise, bogus trailing tokens, Sr./Jr. expansion, and title case.
Applied on API serialization and at resume ingest so new rows stay clean.
"""
from __future__ import annotations

import re

# Leading filler often pasted from summary lines
_RE_LEADING_FILLER = re.compile(
    r"(?is)^\s*(?:"
    r"i\s*['´']m\s+"
    r"|i\s+am\s+"
    r"|(?:i\s*['´']?ve\s+been\s+)?(?:working|employed|serving)\s+as\s+(?:a|an|the)\s+"
    r"|currently\s+(?:a|an|the|working\s+as\s+(?:a|an|the)\s+)?"
    r"|(?:acting|serving)\s+as\s+(?:a|an|the)\s+"
    r"|(?:experienced|skilled|passionate)\s+"
    r"|seeking\s+(?:a|an|the|position\s+as\s+(?:a|an|the)\s+)?"
    r"|looking\s+for\s+(?:a|an|the\s+)?(?:role\s+as\s+(?:a|an|the)\s+)?"
    r")\s*",
)

_RE_LEADING_ARTICLE = re.compile(r"(?i)^(a|an|the)\s+")

# Employment / location tails (company names, etc.)
_RE_TAIL_CLAUSE = re.compile(
    r"(?is)\s+(?:at|@|for|with|since|from|based\s+in|,)\s.*$",
)

# Dash or en-dash then company / location (no "at")
_RE_TAIL_DASH_ORG = re.compile(r"(?is)\s+[-–—]\s+[A-Za-z0-9].*$")

# Legal suffix clutter at end
_RE_TAIL_LEGAL = re.compile(
    r"(?is)\s*,?\s*(?:inc\.?|llc\.?|ltd\.?|plc\.?|gmbh|corp\.?|corporation|company|co\.)\b.*$",
)

_RE_PAID_PREFIX = re.compile(r"(?i)^paid\s+(?=(?:media|marketing|social|digital)\b)")

# Sr. / Jr. before title case (avoid matching "Sr" and leaving a stray ".")
_RE_SR = re.compile(r"(?i)\bsr\.?(?=\s|$)")
_RE_JR = re.compile(r"(?i)\bjr\.?(?=\s|$)")

_SMALL_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "to",
        "for",
        "with",
        "on",
        "vs",
        "at",
        "as",
    }
)

_ACRONYMS_LOWER = frozenset(
    {
        "qa",
        "ui",
        "ux",
        "api",
        "ml",
        "ai",
        "dba",
        "devops",
        "hr",
        "it",
        "pm",
        "vp",
        "cto",
        "ceo",
        "cfo",
        "sre",
        "sdet",
        "bi",
    }
)

# If the word before the last token is one of these, the last token may be company / garbage.
_HEAD_ROLE_WORDS = frozenset(
    {
        "engineer",
        "developer",
        "scientist",
        "manager",
        "specialist",
        "architect",
        "designer",
        "analyst",
        "consultant",
        "officer",
        "executive",
        "coordinator",
        "administrator",
        "programmer",
        "technician",
        "tester",
        "intern",
        "lead",
        "program",
        "director",
        "head",
        "researcher",
        "strategist",
        "ops",
        "dev",
    }
)

# Tokens we never strip as trailing garbage (languages, stacks, clouds, levels).
_ALLOWED_TRAILING_TOKENS = frozenset(
    {
        "i",
        "ii",
        "iii",
        "iv",
        "v",
        "net",
        "stack",
        "end",
        "python",
        "java",
        "kotlin",
        "scala",
        "ruby",
        "rust",
        "golang",
        "go",
        "node",
        "react",
        "angular",
        "vue",
        "rails",
        "php",
        "swift",
        "objc",
        "aws",
        "gcp",
        "azure",
        "kubernetes",
        "docker",
        "linux",
        "windows",
        "mobile",
        "android",
        "ios",
        "frontend",
        "backend",
        "fullstack",
        "full",
        "data",
        "cloud",
        "security",
        "learning",
        "intelligence",
        "blockchain",
        "embedded",
        "firmware",
        "hardware",
        "mechanical",
        "electrical",
        "financial",
        "product",
        "project",
        "scrum",
        "agile",
        "remote",
        "hybrid",
        "contract",
        "part",
        "time",
        "staff",
        "principal",
        "senior",
        "junior",
        "mid",
        "entry",
        "level",
        "software",
        "web",
        "application",
        "applications",
        "systems",
        "system",
        "quality",
        "machine",
        "deep",
        "nlp",
        "etl",
        "media",
        "digital",
        "paid",
        "growth",
        "marketing",
        "sales",
        "support",
        "success",
        "experience",
        "ux",
        "ui",
        "ai",
        "ml",
    }
)

_RE_ROLE_IN_SEGMENT = re.compile(
    r"(?i)\b(?:engineer|developer|analyst|scientist|manager|specialist|consultant|architect|designer|"
    r"programmer|researcher|intern|tester|lead|director|strategist|officer|executive|coordinator)\b",
)


def _pick_pipe_title_segment(t: str) -> str:
    """CV lines like 'Name | Sr Engineer | Company' → keep the segment that looks like a job title."""
    if "|" not in t:
        return t
    parts = [p.strip() for p in re.split(r"\s*\|\s*", t) if p.strip()]
    if not parts:
        return t
    for p in parts:
        if _RE_ROLE_IN_SEGMENT.search(p) and len(p.split()) <= 12:
            return p
    return parts[0]


def _strip_trailing_noise_tokens(words: list[str]) -> list[str]:
    """Remove company / typo tokens after a clear role head (e.g. '... Engineer emiiq' → engineer)."""
    out = list(words)
    for _ in range(4):
        if len(out) < 2:
            break
        prev = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", out[-2], flags=re.I).lower()
        if "/" in prev:
            prev = prev.split("/")[-1]
        if prev not in _HEAD_ROLE_WORDS:
            break
        last = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", out[-1], flags=re.I)
        low = last.lower()
        if low in _ALLOWED_TRAILING_TOKENS:
            break
        if re.match(r"^(i{1,3}|iv|v|vi{0,3}|ix|x)$", low, re.I):
            break
        # Garbage / unknown company slug: short alphabetic token
        if re.match(r"^[a-z]{2,10}$", low) and low not in _ALLOWED_TRAILING_TOKENS:
            out.pop()
            continue
        break
    return out


def _cap_token(tok: str, index: int) -> str:
    if not tok:
        return tok
    if "/" in tok:
        return "/".join(_cap_token(p, index) for p in tok.split("/"))
    if "-" in tok:
        return "-".join(_cap_token(p, index) for p in tok.split("-"))
    low = tok.lower()
    if index > 0 and low in _SMALL_WORDS:
        return low
    if low in _ACRONYMS_LOWER:
        return low.upper()
    if 2 <= len(tok) <= 5 and tok.isalpha() and tok.isupper():
        return tok.upper()
    if len(tok) == 1:
        return tok.upper()
    return tok[0].upper() + tok[1:].lower() if len(tok) > 1 else tok.upper()


def title_case_professional(s: str) -> str:
    """Title-case a job title; keeps small words lower mid-sentence; handles UI/UX, hyphens."""
    s = re.sub(r"\s+", " ", (s or "").strip())
    if not s:
        return ""
    parts = s.split()
    return " ".join(_cap_token(p, i) for i, p in enumerate(parts))


def polish_candidate_title(raw: str) -> str:
    """
    Strip boilerplate, company tails, pipe noise, trailing garbage; Sr./Jr.; title case.
    """
    if not isinstance(raw, str):
        return ""
    t = raw.strip()
    if not t or t.lower() == "unknown":
        return ""
    t = _pick_pipe_title_segment(t)
    t = _RE_LEADING_FILLER.sub("", t)
    t = _RE_LEADING_ARTICLE.sub("", t)
    t = _RE_TAIL_CLAUSE.sub("", t)
    t = _RE_TAIL_DASH_ORG.sub("", t)
    t = _RE_TAIL_LEGAL.sub("", t)
    t = _RE_PAID_PREFIX.sub("", t)
    t = _RE_SR.sub("Senior", t)
    t = _RE_JR.sub("Junior", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    words = t.split()
    if len(words) > 10:
        words = words[-8:]
    words = _strip_trailing_noise_tokens(words)
    t = " ".join(words)
    if not t:
        return ""
    return title_case_professional(t)


def polish_role_fine_display(raw: str) -> str:
    v = (raw or "").strip()
    if not v or v.lower() == "unknown":
        return v
    return title_case_professional(v.lower())
