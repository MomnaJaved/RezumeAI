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
    "trainee",
    "apprentice",
    "associate",
    "architect",
    "tester",
    "qa",
    "sqa",
    "media",
    "marketing",
    "coordinator",
    "director",
    "assistant",
    "representative",
    "accountant",
    "recruiter",
}

RE_EMAIL = re.compile(r"(email|@|linkedin|github|www|http)", re.IGNORECASE)
RE_MULTI_SPACE = re.compile(r"\s+")
RE_NON_WORD = re.compile(r"[^a-z0-9\+\#\.\s\-\/]", re.IGNORECASE)
# Include zero-width chars that PDFs insert between header fields.
RE_SPLIT_TITLE = re.compile(r"[|•·\u2022\u200b\u200c\u200d\ufeff\u00ad]+|\t+| {2,}|[\u2014\u2013-]{2,}")

# Broad role patterns covering tech + business + ops + HR + sales domains.
RE_TITLE_PHRASE = re.compile(
    r"\b("
    r"(?:senior|sr\.?|junior|jr\.?|lead|principal|associate|assistant|head\s+of)?\s*"
    r"(?:software|backend|frontend|full\s*stack|fullstack|web|mobile|android|ios|data|ml|ai|qa|sqa|ui/ux|ux/ui|ui|ux"
    r"|sales|digital|content|graphic|product|business|financial|hr|human\s+resources|operations|devops"
    r"|cloud|cyber|network|system|project|marketing|customer|account|talent|supply\s+chain)?\s*"
    r"(?:software\s+engineering\s+trainee|engineering\s+trainee|"
    r"engineer|developer|designer|analyst|scientist|manager|tester|intern|trainee|apprentice|architect"
    r"|executive|specialist|consultant|coordinator|officer|director|associate|representative"
    r"|accountant|recruiter|strategist|lead)"
    r")\b",
    re.IGNORECASE,
)

# Matches "Results-driven Sales Executive with …" or "Experienced Product Manager who …"
RE_SUMMARY_TITLE = re.compile(
    r"\b(?:results[- ]driven|experienced|motivated|highly\s+skilled|skilled|seasoned|dedicated|passionate|accomplished|proven|versatile|dynamic)\s+"
    r"([A-Za-z][A-Za-z /&+\-]{2,60}?)"
    r"(?=\s+with\b|\s+who\b|\s+seeking\b|\s+looking\b)",
    re.IGNORECASE,
)

# Matches "X years of experience as a Product Manager working in …"
RE_EXP_AS_TITLE = re.compile(
    r"\b(?:\d{1,2}(?:\.\d)?\+?\s*years?\s+(?:of\s+)?)?experience\s+as\s+(?:an?\s+)?"
    r"([A-Za-z][A-Za-z /&+\-]{2,60}?)"
    r"(?=\s+(?:working|in\b|at\b|for\b|with\b|since\b)|[.,;\n]|$)",
    re.IGNORECASE,
)
# Matches "working/worked as a/an <Title>"
RE_WORKING_AS_TITLE = re.compile(
    r"\b(?:worked|working|serve(?:d|s)?|serving)\s+as\s+(?:an?\s+|the\s+)?"
    r"([A-Za-z][A-Za-z /&+\-]{2,60}?)"
    r"(?=\s+(?:working|at\b|in\b|for\b|with\b)|[.,;\n]|$)",
    re.IGNORECASE,
)


def _clean_line(s: str) -> str:
    s = RE_NON_WORD.sub(" ", (s or "").lower())
    s = RE_MULTI_SPACE.sub(" ", s).strip()
    return s


def extract_title_from_raw(raw_text: str) -> str:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return "unknown"

    t = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip PII placeholders inserted by strip_pii() so they don't cause chunk-skipping.
    t = re.sub(r"\[(?:email|e-mail|phone|tel|mobile|address|contact|number)[^\]]*\]", " ", t, flags=re.IGNORECASE)
    # Convert PDF zero-width chars to pipe separators so RE_SPLIT_TITLE can break them.
    t = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]+", " | ", t)
    # Inject line breaks before common section headers when text is collapsed.
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
                for pat in (RE_SUMMARY_TITLE, RE_EXP_AS_TITLE, RE_WORKING_AS_TITLE, RE_TITLE_PHRASE):
                    m = pat.search(l_clean)
                    if m:
                        cand = _clean_line(m.group(1))
                        words = cand.split()
                        if 1 <= len(words) <= 6 and any(w in ROLE_KEYWORDS for w in words):
                            return cand
                continue

            words = l_clean.split()

            # title should be 2–6 words
            if len(words) < 2 or len(words) > 6:
                for pat in (RE_SUMMARY_TITLE, RE_EXP_AS_TITLE, RE_WORKING_AS_TITLE, RE_TITLE_PHRASE):
                    m = pat.search(l_clean)
                    if m:
                        cand = _clean_line(m.group(1))
                        cwords = cand.split()
                        if 1 <= len(cwords) <= 6 and any(w in ROLE_KEYWORDS for w in cwords):
                            return cand
                continue

            # must contain role keyword; if the chunk also has name/location words,
            # prefer a shorter RE_TITLE_PHRASE sub-match over returning the full chunk.
            if any(w in ROLE_KEYWORDS for w in words):
                m = RE_TITLE_PHRASE.search(l_clean)
                if m:
                    cand = _clean_line(m.group(1))
                    cwords = cand.split()
                    # Use the sub-match only when it is shorter (avoids "sana malik data scientist")
                    if 1 <= len(cwords) < len(words) and any(w in ROLE_KEYWORDS for w in cwords):
                        return cand
                return " ".join(words)

    # Fallback: scan first ~5k chars using all patterns.
    head = _clean_line(t[:5000])
    for pat in (RE_SUMMARY_TITLE, RE_EXP_AS_TITLE, RE_WORKING_AS_TITLE, RE_TITLE_PHRASE):
        m = pat.search(head)
        if m:
            cand = _clean_line(m.group(1))
            words = cand.split()
            if 1 <= len(words) <= 6 and any(w in ROLE_KEYWORDS for w in words):
                return cand

    return "unknown"
