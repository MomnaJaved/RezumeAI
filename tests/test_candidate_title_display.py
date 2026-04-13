from __future__ import annotations

from api.services.candidate_title_display import polish_candidate_title, title_case_professional


def test_polish_filler_and_paid_media():
    assert polish_candidate_title("working as a paid media specialist") == "Media Specialist"


def test_polish_title_case_engineer():
    assert polish_candidate_title("associate software engineer") == "Associate Software Engineer"


def test_title_case_small_words():
    assert title_case_professional("engineer of things and stuff") == "Engineer of Things and Stuff"


def test_polish_unknown_empty():
    assert polish_candidate_title("unknown") == ""
    assert polish_candidate_title("") == ""


def test_polish_trailing_garbage_after_engineer():
    assert polish_candidate_title("associate ai/ml engineer emiiq") == "Associate AI/ML Engineer"


def test_polish_sr_and_company_tail():
    assert polish_candidate_title("sr. software engineer at Google LLC") == "Senior Software Engineer"


def test_polish_pipe_cv_segment():
    assert polish_candidate_title("John Doe | Sr. Software Engineer | Acme Corp") == "Senior Software Engineer"
