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

# Stored in DB / APIs when we could not infer a name (use empty, not a sentence label).
UNKNOWN_CANDIDATE = ""


def _collapse_ocr_header_letter_spacing(line: str) -> str:
    """
    Fix Tesseract-style letter-spacing: ``J o h n   S m i t h`` → ``John Smith``.

    When words are separated by **two or more spaces** but letters within a word
    are separated by single spaces, join single-letter tokens per group. Safe
    for normal text: requires a majority of single-character alphabetic tokens
    inside each whitespace-delimited group.
    """
    s = (line or "").strip()
    if not s or len(s) < 5:
        return s
    # Keep pipe-separated header fields aligned with RE_HEADER_SPLIT downstream.
    if "|" in s:
        parts = [p.strip() for p in re.split(r"\s*\|\s*", s) if p.strip()]
        return " | ".join(_collapse_ocr_header_letter_spacing(p) for p in parts).strip(" |")

    pieces = re.split(r"\s{2,}", s)
    if len(pieces) <= 1:
        return s

    rebuilt: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        toks = piece.split()
        if not toks:
            continue
        singles = sum(1 for t in toks if len(t) == 1 and t.isalpha())
        if len(toks) >= 3 and singles >= max(3, int(len(toks) * 0.55)):
            rebuilt.append("".join(toks))
        else:
            rebuilt.append(piece)
    if not rebuilt:
        return s
    return " ".join(rebuilt)

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
# Include zero-width chars (U+200B/C/D, BOM, soft-hyphen) which PDFs insert between fields.
RE_HEADER_SPLIT = re.compile(r"[|•·\u2022\u200b\u200c\u200d\ufeff\u00ad]+|\t+| {3,}")
RE_NAME_LABEL = re.compile(
    r"^\s*(?:full\s*name|name|candidate(?:\s+name)?)\s*[:;]\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Search variant — no ^ anchor; finds "Name: X" embedded mid-line (e.g. "Finance Analyst Name: Hassan Raza")
RE_NAME_LABEL_SEARCH = re.compile(
    r"(?:full\s*name|name|candidate(?:\s+name)?)\s*[:;]\s*([A-Za-z][A-Za-z .'-]{1,60}?)(?:\s*[|,\u200b]|\s*(?:city|phone|email|address|contact)\b|$)",
    re.IGNORECASE,
)
# Also match PII-stripped placeholders so stored raw_text still signals contact presence.
RE_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+|linkedin\.com|github\.com|http|\[e-?mail\]|\[email\s*address\]", re.IGNORECASE)
# First real mailbox only (``RE_EMAIL`` can match ``linkedin.com`` / ``http`` before the @-address on one line).
RE_AT_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}")
RE_PHONEISH = re.compile(r"\b\+?\d[\d\s().-]{7,}\d\b|\[phone\]|\[tel\]|\[mobile\]|\[contact\]|\[cell\]|\[number\]", re.IGNORECASE)
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
        # Team / collaboration phrases sometimes appear near the top (or in OCR merges)
        # and can match the name heuristics if not blocked.
        "frontend and backend teams",
        "frontend and backend team",
        "backend and frontend teams",
        "backend and frontend team",
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
        # Role / org tokens that should never constitute a person's name.
        "frontend",
        "backend",
        "fullstack",
        "full-stack",
        "team",
        "teams",
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
        # Action verbs common in bullet-point descriptions (prevent phrases like
        # "Converting leads into clients" from being treated as a name)
        "converting", "developing", "managing", "managing", "achieving", "handling",
        "leading", "building", "implementing", "driving", "supporting", "delivering",
        "ensuring", "maintaining", "creating", "improving", "overseeing", "preparing",
        "assisted", "achieved", "responsible", "collaborated", "coordinated",
        "clients", "vendors", "stakeholders", "targets", "pipelines",
    }
)

# Common location tokens that appear on the same header line as the person's name.
_TRAILING_LOCATION_TOKEN = frozenset(
    {
        "lahore",
        "karachi",
        "islamabad",
        "rawalpindi",
        "faisalabad",
        "multan",
        "peshawar",
        "quetta",
        "sialkot",
        "gujranwala",
        "hyderabad",
        "pakistan",
        "india",
        "uae",
        "dubai",
        "riyadh",
        "jeddah",
        "uk",
        "usa",
        "canada",
    }
)


def _looks_like_ocr_name_garbage(name: str) -> bool:
    """
    Reject fragments Tesseract often leaves (e.g. ``x oe Ss``) that pass token checks
    or lines where no token looks like a real name word.
    """
    s = (name or "").strip()
    if not s:
        return True
    parts = s.split()
    one_char_lower = False
    for p in parts:
        core = re.sub(r"^[^\w'’.-]+|[^\w'’.-]+$", "", p, flags=re.UNICODE)
        if not core:
            continue
        if len(core) == 1 and core.isalpha() and core.islower():
            one_char_lower = True
            break
    if one_char_lower:
        return True
    # Three or more "words" with no part ≥4 letters (unless ALLCAPS header) = noise.
    if len(parts) >= 3:
        any_lower = any(c.islower() for c in s if c.isalpha())
        max_letters = 0
        for p in parts:
            L = re.sub(r"[^A-Za-z]", "", p)
            max_letters = max(max_letters, len(L))
        if any_lower and max_letters < 4:
            return True
    return False


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
    # Single-letter initial (J), initial with period (J.), or two-letter given names (Li, Yu).
    if len(w) == 1 and w[0].isalpha():
        return True
    if len(w) == 2 and w[0].isalpha():
        if w[1] == ".":
            return True
        if w[1].isalpha():
            return w.lower() not in ("jr", "sr")
        return False
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

    # Trim trailing location/role tokens glued to the name
    # e.g., "Hassan Ali Lahore" → "Hassan Ali"  |  "Sana Malik Data Scientist" → "Sana Malik"
    _TRAILING_TRIM = _TRAILING_LOCATION_TOKEN | ROLE_KEYWORDS | {
        "data", "machine", "artificial", "digital", "senior", "junior", "lead",
        "principal", "chief", "head", "product", "business", "content", "cloud",
        "cyber", "network", "system", "project", "supply", "chain", "human",
        "resources", "resource", "financial", "graphic", "software", "mobile",
        "android", "ios", "web", "fullstack", "backend", "frontend",
    }
    out_parts = out.split()
    while len(out_parts) > 2 and out_parts[-1].lower() in _TRAILING_TRIM:
        out_parts.pop()
    if len(out_parts) < 2:
        return ""
    out = " ".join(out_parts).strip()

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
        # Department / domain qualifiers that appear in filenames like "Hassan_Finance.pdf"
        "finance",
        "hr",
        "ops",
        "operations",
        "tech",
        "dev",
        "ui",
        "ux",
        "sales",
        "marketing",
        "admin",
        "it",
        "engineering",
        "accounts",
        "account",
        "design",
        "data",
        "devops",
        "qa",
        "sqa",
        "product",
        "manager",
        "analyst",
        "executive",
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


def _name_prefix_left_of_at_email(ch: str) -> str:
    """
    Return text to the left of the first *@-address* in ``ch``, minus a trailing
    "Email:" / "Phone:" label. Handles::

        Ahsan Farhan Sherazi  Email: ahsanfarhansherazi02@gmail.com

    ``RE_EMAIL`` must not be used for the cut: it can match ``linkedin.com``
    first on the same line as the real mailbox.
    """
    m = RE_AT_EMAIL.search(ch)
    if not m or m.start() <= 0:
        return ""
    left = ch[: m.start()].strip(" ,|•-–\t")
    left = re.sub(
        r"\s+(?:e-?mail|email|phone|tel|mobile|cell|whatsapp)\s*:\s*$",
        "",
        left,
        flags=re.IGNORECASE,
    ).strip(" ,|•-–\t")
    return left


def _text_before_email_label(ch: str) -> str:
    """
    Text before an ``E-mail:`` / ``Email:`` keyword when Tesseract did not keep an ``@`` on
    the same line, or the @-token pattern did not match.
    """
    m = re.search(
        r"(?i)E-?\s*mails?\s*:\s*",
        ch,
    )
    if not m or m.start() < 1:
        return ""
    return ch[: m.start()].strip(" |·•,;\t-–")


def _name_before_trailing_linkedin_url(ch: str) -> str:
    """E.g. ``Ahsan Farhan Sherazi linkedin.com/in/...`` (no @ on this segment)."""
    m = re.search(
        r"(?i)linkedin\.com/\S*",
        ch,
    )
    if not m or m.start() < 2:
        return ""
    return ch[: m.start()].strip(" ,|·•\t-–")


def _name_before_first_phoneish(ch: str) -> str:
    """E.g. ``Ahsan Farhan Sherazi +92-317-0000000`` (common camera scans)."""
    # ``RE_PHONEISH`` can miss ``+`` at a non-\\b boundary (space to ``+`` is not a "word" boundary in regex).
    m = re.search(
        r"(?i)(\+?\d[\d\s().-]{7,32}\d)(?=\s|$)",
        ch,
    )
    if m is None:
        m = RE_PHONEISH.search(ch)
    if not m or m.start() < 1:
        return ""
    return ch[: m.start()].rstrip(" ,;:|·•\t-–")


def _name_from_contact_line_chunk(ch: str) -> str:
    """Heuristics for a header fragment with email / phone / LinkedIn (OCR may omit ``@``)."""
    for fn in (
        _name_prefix_left_of_at_email,
        _text_before_email_label,
        _name_before_trailing_linkedin_url,
        _name_before_first_phoneish,
    ):
        s = fn(ch)
        if 2 < len(s) <= 120:
            return s
    return ""


def _header_name_line_fallback(ln: str) -> str:
    """
    Last-resort: 2-5 space-separated alpha words, after stripping obvious non-name lead-in.
    """
    s0 = (ln or "").strip()
    if not s0 or len(s0) < 3:
        return ""
    s = _name_from_contact_line_chunk(s0) or s0
    s = s.strip(" ,;|")
    if re.search(r"(?i)https?://", s):
        s = re.split(r"(?i)https?://", s, maxsplit=1)[0].strip()
    low = s.lower()
    for bad in (
        "education", "experience", "summary", "objective", "university", "bachelor",
        "technical", "skills", "certif", "projects", "contact", "curriculum", "page",
    ):
        if low == bad or low.startswith(bad + " "):
            return ""
    if s.isupper() and len(s) > 24 and re.search(
        r"\b(INC|LLC|LABS?|UNIVERSITY|COLLEGE|INSTITUTE|TECHNOLOG|SYSTEMS?)\b",
        s,
    ):
        return ""
    parts = s.split()
    if not 2 <= len(parts) <= 5:
        return ""
    for p in parts:
        if not re.match(r"^[A-Za-z][A-Za-z'.-]*$", p) or not (1 < len(p) < 28):
            return ""
    return _normalize_name_parts(" ".join(parts)) or ""


def extract_name_from_raw(raw_text: str, *, max_lines: int = 40) -> str:
    """
    Return best-effort full name, or "" if none found.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return ""

    t = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # PDF zero-width chars glue fields together; convert to pipe separators so
    # RE_HEADER_SPLIT (and later line splitting) can separate them correctly.
    t = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]+", " | ", t)
    # Stored raw_text is often PII-stripped with newlines collapsed to spaces; pipe-separated
    # headers ("Name | Title | …") then become one long line — split those back out.
    if t.count("\n") < 4 and "|" in t:
        t = re.sub(r"\s*\|\s*", "\n", t, count=24)

    # Before scanning lines: check for "belongs to" / "resume of" patterns anywhere in the text.
    # Some CVs hide the name at the very end: "This resume belongs to: — Muhammad Usman Ali —"
    _RE_BELONGS_TO = re.compile(
        r"(?:this\s+resume\s+(?:belongs\s+to|is\s+of)|resume\s+of|prepared\s+by)\s*[:\-–—]*\s*"
        r"[—–\-]*\s*([A-Za-z][A-Za-z .'-]{3,50}?)\s*[—–\-]*\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    _belongs_match = _RE_BELONGS_TO.search(t)

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()][:max_lines]
    # OCR: letter-spaced names are almost always in the first few lines.
    lines = [
        _collapse_ocr_header_letter_spacing(ln) if i < 8 else ln
        for i, ln in enumerate(lines)
    ]

    def ok_candidate(val: str) -> bool:
        if not val:
            return False
        if val.strip().lower() in ("candidate", "unknown candidate", "unknown"):
            return False
        if _looks_like_ocr_name_garbage(val):
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
            # Also search mid-line for "Finance Analyst Name: Hassan Raza | City: ..."
            m = RE_NAME_LABEL_SEARCH.search(ln)
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
            if not ch:
                continue
            # Long "Name + Email: very-long-local@..." lines must not be dropped (old limit 70).
            ch_max = 220 if ("@" in ch or "mail" in ch.lower()) else 88
            if len(ch) > ch_max:
                continue
            if RE_EMAIL.search(ch) or RE_PHONEISH.search(ch):
                # Tesseract often drops ``@`` or reorders; try @-cut, "Email:" left, linkedin, phone, etc.
                prefix = _name_from_contact_line_chunk(ch)
                if 3 <= len(prefix) <= 100:
                    vpre = _normalize_name_parts(prefix)
                    if ok_candidate(vpre):
                        pscore = 80 - i * 2 + 10
                        if line_has_contact:
                            pscore += 12
                        pscore += max(0, 6 - j * 2)
                        found.append((pscore, vpre))
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

    # "Belongs to" / "resume of" match is high-confidence; add it now.
    if _belongs_match:
        val = _normalize_name_parts(_belongs_match.group(1).strip())
        if ok_candidate(val):
            found.append((95, val))

    # 4) Whole line fallbacks: OCR reordered the header, or the line failed chunk limits above.
    if not found:
        for i, ln in enumerate(lines[:10]):
            prefix = _name_from_contact_line_chunk(ln)
            if 3 <= len(prefix) <= 100:
                val = _normalize_name_parts(prefix)
                if ok_candidate(val):
                    found.append((42 - i, val))
    if not found:
        for i, ln in enumerate(lines[:8]):
            val = _header_name_line_fallback(ln)
            if val and ok_candidate(val):
                found.append((30 - i, val))

    if not found:
        return ""

    # Choose best-scoring unique candidate. Require a minimum confidence to avoid false positives.
    found.sort(key=lambda t: (-t[0], t[1]))
    best_score, best = found[0]
    # Legacy whole-line path uses (40 - line_index); a name on line 2 can score 39. Threshold 35 keeps those.
    if best_score < 35:
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
    Resolve stored candidate full_name: resume header first, then email local-part, else empty string.
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
