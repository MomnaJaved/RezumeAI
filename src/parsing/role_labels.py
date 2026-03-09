"""
Map parsed/inferred title to role_label for software houses with multiple departments.

Two modes:
- "engineering_only": 3 classes — frontend, backend, fullstack (for engineering-only pipelines).
- "multi_department": broader set — frontend, backend, fullstack, devops, qa, data, design,
  product, marketing, hr, operations, other (for routing across departments).
"""
from __future__ import annotations

from typing import Tuple

# ---------------------------------------------------------------------------
# Multi-department: aligns with DEPT_RULES / ROLE_RULES in role_inference.py
# ---------------------------------------------------------------------------
TITLE_TO_ROLE_BROAD: dict[str, str] = {
    # Engineering
    "frontend developer": "frontend",
    "frontend": "frontend",
    "backend developer": "backend",
    "backend": "backend",
    "full stack developer": "fullstack",
    "fullstack developer": "fullstack",
    "full stack": "fullstack",
    "fullstack": "fullstack",
    "software engineer": "fullstack",
    "software developer": "fullstack",
    "mobile developer": "fullstack",
    "devops engineer": "devops",
    "qa engineer": "qa",
    "ui/ux designer": "design",
    "graphic designer": "design",
    "product designer": "design",
    # Data
    "data scientist": "data",
    "data analyst": "data",
    "data engineer": "data",
    "machine learning engineer": "data",
    # Product / Business
    "product manager": "product",
    "product owner": "product",
    "business analyst": "product",
    "business development executive": "marketing",
    "email marketing specialist": "marketing",
    "social media manager": "marketing",
    "digital marketing": "marketing",
    # HR / Ops / Other
    "hr officer": "hr",
    "hr manager": "hr",
    "recruiter": "hr",
    "talent acquisition": "hr",
    "data entry operator": "operations",
    "customer service representative": "operations",
    "operations manager": "operations",
}

# Labels for multi-department (order fixes id mapping)
ROLE_LABELS_MULTI: Tuple[str, ...] = (
    "frontend",
    "backend",
    "fullstack",
    "devops",
    "qa",
    "data",
    "design",
    "product",
    "marketing",
    "hr",
    "operations",
    "other",
)

# ---------------------------------------------------------------------------
# Engineering-only: 3 classes (legacy / when you only care about dev role)
# ---------------------------------------------------------------------------
TITLE_TO_ROLE_ENGINEERING_ONLY: dict[str, str] = {
    "frontend developer": "frontend",
    "frontend": "frontend",
    "backend developer": "backend",
    "backend": "backend",
    "full stack developer": "fullstack",
    "fullstack developer": "fullstack",
    "full stack": "fullstack",
    "fullstack": "fullstack",
    "software engineer": "fullstack",
    "software developer": "fullstack",
    "mobile developer": "fullstack",
    "devops engineer": "backend",
    "qa engineer": "fullstack",
    "ui/ux designer": "frontend",
    "data scientist": "backend",
    "data analyst": "backend",
}

ROLE_LABELS_ENGINEERING_ONLY: Tuple[str, ...] = ("frontend", "backend", "fullstack")

# ---------------------------------------------------------------------------
# Default: multi_department (correct for software houses with several departments)
# ---------------------------------------------------------------------------
USE_MULTI_DEPARTMENT = True  # Set to False for engineering-only 3-class

if USE_MULTI_DEPARTMENT:
    ROLE_LABELS = ROLE_LABELS_MULTI
    TITLE_TO_ROLE = TITLE_TO_ROLE_BROAD
    DEFAULT_ROLE = "other"
else:
    ROLE_LABELS = ROLE_LABELS_ENGINEERING_ONLY
    TITLE_TO_ROLE = TITLE_TO_ROLE_ENGINEERING_ONLY
    DEFAULT_ROLE = "fullstack"


def title_to_role_label(
    title: str,
    *,
    multi_department: bool | None = None,
) -> str:
    """
    Map title string to role_label.
    If multi_department is None, uses global USE_MULTI_DEPARTMENT.
    """
    if not isinstance(title, str) or not title.strip():
        return DEFAULT_ROLE
    t = title.strip().lower()
    use_broad = multi_department if multi_department is not None else USE_MULTI_DEPARTMENT
    mapping = TITLE_TO_ROLE_BROAD if use_broad else TITLE_TO_ROLE_ENGINEERING_ONLY
    labels = ROLE_LABELS_MULTI if use_broad else ROLE_LABELS_ENGINEERING_ONLY
    default = "other" if use_broad else "fullstack"
    return mapping.get(t, default)
