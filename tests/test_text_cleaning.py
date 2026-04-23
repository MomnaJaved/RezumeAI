from src.parsing.text_cleaning import preprocess_resume_text


def test_preprocess_joins_hyphenated_line_break():
    raw = "Full-\nstack developer with Python"
    out = preprocess_resume_text(raw, apply_ocr_heuristics=False)
    assert "Fullstack" in out or "fullstack" in out.lower()
