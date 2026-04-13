from __future__ import annotations

from src.parsing.role_fine import infer_role_fine


def test_intern_maps_to_track_not_intern_label():
    assert infer_role_fine("Software Engineering Intern", "Python, Django", "") == "backend"
    assert infer_role_fine("Engineering Intern", "", "") == "software"


def test_mobile_native_maps_to_software():
    assert infer_role_fine("Android Developer", "Kotlin, Android SDK", "") == "software"


def test_react_native_counts_as_frontend():
    assert infer_role_fine("Mobile Developer", "React Native, TypeScript", "") == "frontend"


def test_qa_intern_stays_qa():
    assert infer_role_fine("QA Intern", "Selenium", "") == "qa"
