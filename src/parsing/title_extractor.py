from __future__ import annotations
import re

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
    "media",
    "marketing",
}

RE_EMAIL = re.compile(r"(email|@|linkedin|github|www|http)", re.IGNORECASE)
RE_MULTI_SPACE = re.compile(r"\s+")
RE_NON_WORD = re.compile(r"[^a-z0-9\+\#\.\s\-\/]", re.IGNORECASE)
RE_SPLIT_TITLE = re.compile(r"[|•·\u2022]+| {2,}|[\u2014\u2013-]{2,}")  # bullets, multi-space, long dashes

# Common title patterns even when embedded in a long line.
RE_TITLE_PHRASE = re.compile(
    r"\b("
    r"(?:senior|sr\.?|junior|jr\.?|lead|principal|associate|assistant)?\s*"
    r"(?:software|backend|frontend|full\s*stack|fullstack|web|mobile|android|ios|data|ml|ai|qa|sqa|ui/ux|ux/ui|ui|ux)?\s*"
    r"(?:engineer|developer|designer|analyst|scientist|manager|tester|intern|architect)"
    r")\b",
    re.IGNORECASE,
)


def _clean_line(s: str) -> str:
    s = RE_NON_WORD.sub(" ", (s or "").lower())
    s = RE_MULTI_SPACE.sub(" ", s).strip()
    return s


def extract_title_from_raw(raw_text: str) -> str:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return "unknown"

    # If PDF extraction collapsed into one long line, inject some breaks around common headers.
    t = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"(?i)\s+(?=(work experience|professional experience|employment history|experience|education|skills)\b)", "\n", t)

    lines = t.splitlines()[:60]  # top part is usually enough

    for line in lines:
        l = line.strip()
        if not l:
            continue

        # Split compact lines into smaller chunks (some CVs have: "Name | Title | ...")
        chunks = [c.strip() for c in RE_SPLIT_TITLE.split(l) if c.strip()] or [l]
        for ch in chunks:
            l_clean = _clean_line(ch)

            # skip emails, links, contact info
            if RE_EMAIL.search(l_clean):
                continue

            # reject very long chunks (but allow scanning for a title phrase within)
            if len(l_clean) > 90:
                m = RE_TITLE_PHRASE.search(l_clean)
                if m:
                    cand = _clean_line(m.group(1))
                    words = cand.split()
                    if 1 < len(words) <= 6 and any(w in ROLE_KEYWORDS for w in words):
                        return cand
                continue

            words = l_clean.split()

            # title should be 2–6 words
            if len(words) < 2 or len(words) > 6:
                # try an embedded phrase
                m = RE_TITLE_PHRASE.search(l_clean)
                if m:
                    cand = _clean_line(m.group(1))
                    cwords = cand.split()
                    if 1 < len(cwords) <= 6 and any(w in ROLE_KEYWORDS for w in cwords):
                        return cand
                continue

            # must contain role keyword
            if any(w in ROLE_KEYWORDS for w in words):
                return " ".join(words)

    # Fallback: scan first ~5k chars for any title phrase.
    head = _clean_line(t[:5000])
    m = RE_TITLE_PHRASE.search(head)
    if m:
        cand = _clean_line(m.group(1))
        words = cand.split()
        if 1 < len(words) <= 6 and any(w in ROLE_KEYWORDS for w in words):
            return cand

    return "unknown"
