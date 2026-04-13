from __future__ import annotations

import re


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


RE_QA = re.compile(r"\b(qa|sqa|test(er|ing)?|quality assurance|automation|selenium|cypress|playwright|appium|jmeter|k6)\b")
RE_BACKEND = re.compile(
    r"\b(backend|api|microservices?|django|flask|fastapi|spring|node(\.js)?|express|nest|laravel|rails|postgres|mysql|mongodb)\b"
)
RE_FRONTEND = re.compile(
    r"\b(frontend|react(?:\s+native)?|angular|vue|next\.js|nuxt|flutter|typescript|ui|ux|css|html|tailwind|bootstrap)\b"
)
RE_MOBILE = re.compile(r"\b(android|ios|swift|kotlin|xamarin|ionic)\b")
RE_DATA = re.compile(r"\b(data (engineer|science|scientist)|ml|machine learning|deep learning|pytorch|tensorflow|nlp)\b")


def infer_role_fine(title: str, skills: str, raw_hint: str = "") -> str:
    """
    Return a fine-grained role label used for UI filters.
    This is intentionally heuristic and conservative.
    """
    t = _norm(title)
    s = _norm(skills)
    h = _norm(raw_hint)
    blob = " ".join([t, s, h]).strip()

    if not blob:
        return "unknown"

    # If the title itself is QA/testing, classify as QA.
    if RE_QA.search(t):
        return "qa"

    # Determine FE/BE primarily from skills + hint text.
    hint_stack = " ".join([s, h])
    is_be = bool(RE_BACKEND.search(hint_stack))
    is_fe = bool(RE_FRONTEND.search(hint_stack))
    if is_be and is_fe:
        return "fullstack"
    if is_be:
        return "backend"
    if is_fe:
        return "frontend"

    # Generic software titles
    if any(k in t for k in ("software engineer", "associate software engineer", "developer", "engineer")):
        return "software"

    if RE_DATA.search(blob):
        return "data"

    # Mobile-native stack without a clearer FE/BE split → generic software (not a separate UI bucket).
    if RE_MOBILE.search(blob):
        return "software"

    # If not a software title, allow QA from skills/hints.
    if RE_QA.search(" ".join([s, h])):
        return "qa"

    return "other"

