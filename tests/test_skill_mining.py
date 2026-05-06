"""Tests for skill candidate extraction and social-paste sanitization."""

from __future__ import annotations

from src.parsing.skill_mining import extract_skill_candidates, sanitize_text_for_skill_extraction


def test_sanitize_drops_linkedin_footer_and_ads():
    blob = """
Web Design
Figma (Software)
Adobe Photoshop

Don't want to see this
Your feedback will help us improve your experience
It's annoying or not interesting

About
Accessibility
Talent Solutions
Community Guidelines
Careers
Marketing Solutions
Ad Choices
Advertising
Sales Solutions
Mobile
Small Business
Safety Center
Visit our Help Center.
Manage your account and privacy
Go to your Settings.

User Interface Design
React
"""
    cleaned = sanitize_text_for_skill_extraction(blob)
    assert "Don't want to see" not in cleaned
    assert "Accessibility" not in cleaned
    assert "Talent Solutions" not in cleaned
    assert "Visit our Help Center" not in cleaned
    # LinkedIn UI-blob heuristic: drop one-per-line design chips, keep real tech lines.
    assert "Web Design" not in cleaned
    assert "Figma" not in cleaned
    assert "React" in cleaned


def test_extract_skills_after_sanitize_no_footer_phrases():
    text = """
Skills: Figma, Adobe Photoshop

About
Accessibility
Careers
Marketing Solutions

    User experience design
    conversion rate optimization
"""
    skills = extract_skill_candidates(text)
    assert "accessibility" not in skills
    assert "figma" in skills
    assert "conversion rate optimization" in skills


def test_curly_quotes_ad_copy_and_chips_removed():
    """iOS/LinkedIn curly apostrophes must still match junk patterns; chips drop under UI-blob heuristic."""
    blob = """
Don\u2019t want to see this
Your feedback will help us improve your experience
It\u2019s annoying or not interesting
I\u2019ve seen the same ad too often
Web Design
Figma (Software)
Talent Solutions
Community Guidelines
Marketing Solutions
Visit our Help Center.
Oliver Kenyon
GFUEL
13 years turning clicks into customers with CRO
Clients include Portland Leather
4+ yrs designing high-conversion websites & dashboards (Figma)
React
"""
    skills = extract_skill_candidates(blob)
    assert "figma" not in skills
    assert "web design" not in skills
    assert "accessibility" not in skills
    assert "cro" not in skills
    assert "conversion rate optimization" not in skills


def test_inline_junk_in_comma_list_filtered():
    # If ad copy lands on the same section line as real tokens, is_noise should drop the junk fragment.
    skills = extract_skill_candidates("Skills: Figma, Don't want to see this, React\n")
    joined = " ".join(skills).lower()
    assert "don't want to see this" not in joined
    assert "figma" in skills
    assert "react" in skills
