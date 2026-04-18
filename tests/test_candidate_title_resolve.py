from __future__ import annotations

from src.parsing.candidate_title_resolve import display_title_for_candidate_row, resolve_title_from_resume_text


def test_fresher_override():
    t = resolve_title_from_resume_text(
        "Computer Science graduate.\nProjects: todo app in React.",
        "react, javascript",
        None,
        role_label_hint="",
    )
    assert t == "Fresher"


def test_unknown_years_not_forced_to_fresher_when_experience_narrative_has_role():
    text = "Hassan Ali has 1.5 years of experience working as a project coordinator. He assisted in scheduling meetings."
    t = resolve_title_from_resume_text(text, "", None, role_label_hint="")
    assert "coordinator" in t.lower()


def test_display_title_fills_empty_db_title():
    t = display_title_for_candidate_row(
        title="",
        skills="react, node.js, postgresql",
        years_experience=2.0,
        role_label="",
        raw_text="",
    )
    assert "developer" in t.lower() or "engineer" in t.lower() or "stack" in t.lower()


def test_resolve_title_uses_role_hint_when_skills_and_extractor_miss():
    """Sparse CV: no explicit title line, no comma-skills string, but ML role bucket is known."""
    t = resolve_title_from_resume_text(
        "Experienced contributor focused on quality delivery and stakeholder communication.",
        "",
        3.0,
        role_label_hint="frontend",
    )
    assert t == "Frontend Developer"


def test_resolve_title_never_empty_when_polish_would_strip():
    t = resolve_title_from_resume_text(
        "Role: @@@\nSkills: python, django",
        "python, django",
        2.0,
        role_label_hint="backend",
    )
    assert (t or "").strip()


def test_resolve_title_from_experience_narrative_operations_support():
    text = """
SKILLS
Operations Support, Coordination, Reporting
EXPERIENCE
Usman Khan has 2.5 years of experience in operations support roles. He has assisted in daily
operational tasks, vendor coordination, and reporting. His exposure to process optimization and
SOP development is limited.
EDUCATION
BS Business Administration – Karachi University
CERTIFICATIONS
None
"""
    t = resolve_title_from_resume_text(text, "operations support, coordination, reporting", 2.5, role_label_hint="")
    assert "operations" in t.lower() and "support" in t.lower()
