from __future__ import annotations
import re

ROLE_KEYWORDS = {
    "engineer","developer","designer","analyst","scientist","manager",
    "specialist","consultant","officer","executive","lead",
    "intern","associate","architect","tester","qa","sqa"
}

ORG_NOISE = {
    "pvt","ltd","limited","company","solutions","technologies",
    "technology","systems","private","inc","llc","group","labs","studio"
}

RE_MULTI_SPACE = re.compile(r"\s+")
RE_NON_WORD = re.compile(r"[^a-z0-9\+\#\.\s\-\/]", re.IGNORECASE)


def looks_like_sentence(s: str) -> bool:
    # reject long concatenated text or sentences
    if len(s) > 60:
        return True
    if len(s.split()) > 8:
        return True
    if re.search(r"(seeking|looking|dedicated|energetic|motivated)", s):
        return True
    return False


def clean_title(title: str) -> str:
    if not isinstance(title, str):
        return "unknown"

    t = title.strip().lower()
    if not t:
        return "unknown"

    # remove symbols
    t = RE_NON_WORD.sub(" ", t)
    t = RE_MULTI_SPACE.sub(" ", t).strip()

    # reject sentence-like titles
    if looks_like_sentence(t):
        return "unknown"

    words = t.split()

    # remove org noise words
    words = [w for w in words if w not in ORG_NOISE]

    if not words:
        return "unknown"

    # require at least one role keyword
    if not any(w in ROLE_KEYWORDS for w in words):
        return "unknown"

    # keep up to 5 words only
    words = words[:5]

    return " ".join(words)
