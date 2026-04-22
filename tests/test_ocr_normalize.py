from __future__ import annotations

from src.parsing.name_extractor import extract_name_from_raw
from src.parsing.ocr_normalize import normalize_resume_text_for_ocr


def test_normalize_ocr_single_space_ahmad_ali_header():
    """Greedy lookahead used to split after ``Ahma`` (``d`` merged into ``Ali`` run)."""
    raw = "A h m a d A l i\nSoftware Engineer\nlahore@mail.com\n"
    norm = normalize_resume_text_for_ocr(raw)
    assert "Ahmad Ali" in norm.splitlines()[0] or norm.splitlines()[0].startswith("Ahmad")
    assert extract_name_from_raw(norm) == "Ahmad Ali"


def test_normalize_ocr_single_space_john_smith():
    txt = "J o h n S m i t h\nSenior Engineer\njohn.smith@example.com\n"
    norm = normalize_resume_text_for_ocr(txt)
    assert extract_name_from_raw(norm) == "John Smith"


def test_normalize_ocr_single_space_li_ming_short_first():
    raw = "L i M i n g\nData Analyst\nming@corp.io\n"
    norm = normalize_resume_text_for_ocr(raw)
    assert extract_name_from_raw(norm) == "Li Ming"


def test_normalize_ocr_three_part_name_spaced_singles():
    """South Asian / long headers: first + middle + last, all Tesseract single-letter tokens."""
    raw = "A h s a n F a r h a n S h e r a z i\nData Analyst\nahsan@mail.com\n"
    norm = normalize_resume_text_for_ocr(raw)
    assert extract_name_from_raw(norm) == "Ahsan Farhan Sherazi"
    assert "Ahsan Farhan Sherazi" in norm.splitlines()[0]


def test_rejects_ocr_garbage_tokens_as_name():
    from src.parsing.name_extractor import extract_name_from_raw

    # Noise line should not win over a real name on a following line
    lines = "x oe Ss\nAhsan Farhan Sherazi\nAnalyst\n"
    assert extract_name_from_raw(lines) == "Ahsan Farhan Sherazi"
