from __future__ import annotations
import re

ROLE_KEYWORDS = {
    "engineer","developer","designer","analyst","scientist","manager",
    "specialist","consultant","officer","executive","lead",
    "intern","associate","architect","tester","qa","sqa"
}

RE_EMAIL = re.compile(r"(email|@|linkedin|github|www|http)", re.IGNORECASE)
RE_MULTI_SPACE = re.compile(r"\s+")
RE_NON_WORD = re.compile(r"[^a-z0-9\+\#\.\s\-\/]", re.IGNORECASE)


def extract_title_from_raw(raw_text: str) -> str:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return "unknown"

    lines = raw_text.splitlines()[:30]  # only top part of resume

    for line in lines:
        l = line.strip()
        if not l:
            continue

        l_clean = RE_NON_WORD.sub(" ", l.lower())
        l_clean = RE_MULTI_SPACE.sub(" ", l_clean).strip()

        # skip emails, links, contact info
        if RE_EMAIL.search(l_clean):
            continue

        # reject very long lines
        if len(l_clean) > 60:
            continue

        words = l_clean.split()

        # title should be 2–6 words
        if len(words) < 2 or len(words) > 6:
            continue

        # must contain role keyword
        if any(w in ROLE_KEYWORDS for w in words):
            return " ".join(words)

    return "unknown"
