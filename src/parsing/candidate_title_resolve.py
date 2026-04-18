"""
Resolve a meaningful professional title for a candidate (ingest + DB-backed display).

Order of precedence:
1) Fresher — when there is no meaningful professional experience (years None or ~0).
2) Explicit title from résumé text (title_extractor).
3) Title inferred from skills keywords (role_inference.infer_title_from_skills).
4) Headline derived from coarse role_label (frontend/backend/…) when still unknown.
"""
from __future__ import annotations

import re

from src.parsing.role_inference import infer_title_from_skills
from src.parsing.title_extractor import extract_title_from_raw

# Résumé / DB placeholders that should not block inference.
_TITLE_SENTINELS = frozenset(
    {"unknown", "n/a", "na", "tbd", "none", "-", "—", "nil", "null", "title", "your name", "candidate"}
)


def _title_is_meaningful(title: str) -> bool:
    t = (title or "").strip().lower()
    return bool(t) and t not in _TITLE_SENTINELS


def _years_is_fresher(years: float | int | None) -> bool:
    # Unknown years should NOT be treated as fresher. Fresher is a positive signal only when we
    # confidently detect near-zero professional experience.
    if years is None:
        return False
    try:
        y = float(years)
    except (TypeError, ValueError):
        return False
    return y < 0.25


def _polish_inferred_title(s: str) -> str:
    s = (s or "").strip()
    if not s or s.lower() == "unknown":
        return ""
    try:
        from api.services.candidate_title_display import polish_candidate_title

        p = polish_candidate_title(s)
        return p if p else s
    except Exception:
        return s


_RE_EXP_IN_ROLES = re.compile(
    r"\b(?:has\s+)?\d{1,2}(?:\.\d)?\s*\+?\s*years?\s+(?:of\s+)?experience\s+in\s+([A-Za-z][A-Za-z /&+\-]{2,70}?)\s+roles?\b",
    re.IGNORECASE,
)
_RE_EXP_AS_TITLE = re.compile(
    r"\b(?:worked|working|serve(?:d|s)?|serving)\s+as\s+(?:an?\s+|the\s+)?"
    r"([A-Za-z][A-Za-z /&+\-]{2,50}?)"
    r"(?=\s+(?:working|at\b|in\b|for\b|with\b)|[.,;\n]|$)",
    re.IGNORECASE,
)
# "X years of experience as a Product Manager working in…" or just "experience as a …"
_RE_EXP_AS_ROLE = re.compile(
    r"\bexperience\s+(?:of\s+)?as\s+(?:an?\s+)?"
    r"([A-Za-z][A-Za-z /&+\-]{2,50}?)"
    r"(?=\s+(?:working|at\b|in\b|for\b|with\b)|[.,;\n]|$)",
    re.IGNORECASE,
)

_RE_AS_TITLE_GENERIC = re.compile(
    r"\b(?:primarily\s+)?as\s+(?:an?\s+|the\s+)?"
    r"([A-Za-z][A-Za-z /&+\-]{2,50}?)"
    r"(?=\s+(?:working|currently|since|at\b|in\b|for\b|with\b|where\b|who\b|and\b)|[.,;\n]|$)",
    re.IGNORECASE,
)
_RE_ROLE_COLON = re.compile(
    r"^\s*(?:role|position|designation)\s*:\s*([A-Za-z][A-Za-z /&+\-]{2,70})\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_RE_EXPLICIT_FRESHER = re.compile(r"\b(fresher|entry[-\s]?level)\b", re.IGNORECASE)
_RE_GRAD_HINT = re.compile(r"\b(graduate|graduation|student|enthusiast|fresh\s+grad)\b", re.IGNORECASE)
_RE_PROJECTS_HINT = re.compile(r"\b(projects?|portfolio|capstone|hands[-\s]?on\s+experience)\b", re.IGNORECASE)
_RE_EXPLICIT_YEARS_EXP = re.compile(r"\b\d{1,2}(?:\.\d)?\s*\+?\s*years?\s+(?:of\s+)?experience\b", re.IGNORECASE)
_RE_PROFESSIONAL_EXP = re.compile(
    r"\b(worked|working|employed|currently\s+working|professional\s+experience|work\s+experience)\b",
    re.IGNORECASE,
)


def _text_is_probably_fresher(raw_text: str) -> bool:
    t = (raw_text or "").strip()
    if not t:
        return False
    head = t[:8000]
    if _RE_EXPLICIT_FRESHER.search(head):
        return True
    # Graduate/student/enthusiast with no explicit years claim and no professional experience block.
    if _RE_GRAD_HINT.search(head) and not _RE_EXPLICIT_YEARS_EXP.search(head) and not _RE_PROFESSIONAL_EXP.search(head):
        return True
    # Graduate + projects mentioned, no experience claim → fresh grad with side projects.
    if _RE_GRAD_HINT.search(head) and _RE_PROJECTS_HINT.search(head) and not _RE_EXPLICIT_YEARS_EXP.search(head):
        return True
    return False


def _infer_title_from_experience_narrative(raw_text: str) -> str:
    """
    Extract a role title from narrative EXPERIENCE blocks when there is no explicit headline.
    Example: "has 2.5 years of experience in operations support roles" -> "Operations Support".
    """
    t = (raw_text or "").strip()
    if not t:
        return ""
    head = t[:12000]

    for m in (
        _RE_ROLE_COLON.search(head),
        _RE_EXP_IN_ROLES.search(head),
        _RE_EXP_AS_TITLE.search(head),
        _RE_EXP_AS_ROLE.search(head),
        _RE_AS_TITLE_GENERIC.search(head),
    ):
        if not m:
            continue
        cand = (m.group(1) or "").strip()
        if not cand:
            continue
        # Remove trailing fluff ("roles", "role", "position", "functions", "domain", etc.)
        cand = re.sub(r"\b(roles?|role|positions?|position|functions?|domain)\b.*$", "", cand, flags=re.IGNORECASE).strip()
        cand = re.sub(r"\s+", " ", cand).strip()
        if not cand:
            continue
        # Map a few common domain nouns to a role-like headline (avoid returning "Basic Accounting").
        low = cand.lower()
        if low.endswith("accounting"):
            cand = "Accountant"
        elif low.endswith("graphic design"):
            cand = "Graphic Designer"

        # Commonly, we get "operations support" etc. Keep it short and title-like.
        words = cand.split()
        if len(words) > 6:
            cand = " ".join(words[:6])
        return _polish_inferred_title(cand)
    return ""


def _maybe_add_seniority(title: str, years: float | int | None) -> str:
    t = (title or "").strip()
    if not t:
        return ""
    low = t.lower()
    if any(x in low for x in ("senior", "sr.", "lead", "principal", "staff", "head", "director")):
        return t
    try:
        y = float(years) if years is not None else 0.0
    except (TypeError, ValueError):
        y = 0.0
    if y < 7.0:
        return t
    if re.search(r"\b(engineer|developer|designer|analyst|scientist|architect)\b", low):
        return f"Senior {t[0].upper()}{t[1:]}" if t else t
    return t


_ROLE_LABEL_HEADLINE: dict[str, str] = {
    "frontend": "Frontend Developer",
    "backend": "Backend Developer",
    "fullstack": "Software Developer",
    "devops": "DevOps Engineer",
    "qa": "QA Engineer",
    "data": "Data Professional",
    "design": "Design Professional",
    "product": "Product Professional",
    "marketing": "Marketing Professional",
    "hr": "HR Professional",
    "operations": "Operations Professional",
    "other": "Professional",
}


def resolve_title_from_resume_text(
    raw_text: str,
    skills_csv: str,
    years_experience: float | int | None,
    *,
    role_label_hint: str = "",
) -> str:
    """
    Full pipeline for upload-time parsing (raw_text available).
    Never returns an empty string: if polish strips a candidate headline, fall through to the next source.
    """
    if _years_is_fresher(years_experience) or (years_experience is None and _text_is_probably_fresher(raw_text or "")):
        return "Fresher"

    raw_title = extract_title_from_raw(raw_text or "")
    if raw_title and raw_title.lower() != "unknown":
        out = _maybe_add_seniority(_polish_inferred_title(raw_title), years_experience)
        if (out or "").strip():
            return out.strip()

    narr = _infer_title_from_experience_narrative(raw_text or "")
    if narr and narr.lower() != "unknown":
        out = _maybe_add_seniority(narr, years_experience)
        if (out or "").strip():
            return out.strip()

    inf = infer_title_from_skills(skills_csv or "")
    if inf and inf.lower() != "unknown":
        out = _maybe_add_seniority(_polish_inferred_title(inf.replace("_", " ")), years_experience)
        if (out or "").strip():
            return out.strip()

    rl = (role_label_hint or "").strip().lower()
    if rl in _ROLE_LABEL_HEADLINE:
        return _ROLE_LABEL_HEADLINE[rl]
    return "Professional"


def display_title_for_candidate_row(
    *,
    title: str,
    skills: str,
    years_experience: float | int | None,
    role_label: str,
    raw_text: str = "",
) -> str:
    """
    Title for API/ranking when DB `title` may be empty (uses raw_text if provided).
    Does not persist; used to enrich match text and UI reads.
    """
    t = (title or "").strip()
    if _title_is_meaningful(t):
        return t
    if _years_is_fresher(years_experience):
        return "Fresher"
    if (raw_text or "").strip():
        out = resolve_title_from_resume_text(raw_text, skills, years_experience, role_label_hint=role_label)
        if (out or "").strip():
            return out.strip()
    inf = infer_title_from_skills(skills or "")
    if inf and inf.lower() != "unknown":
        out = _maybe_add_seniority(_polish_inferred_title(inf.replace("_", " ")), years_experience)
        if (out or "").strip():
            return out.strip()
    rl = (role_label or "").strip().lower()
    return _ROLE_LABEL_HEADLINE.get(rl, "Professional")
