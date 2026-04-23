from src.parsing.nlp_resume import ResumeNlpEnrichment, merge_skill_candidates


def test_merge_skill_candidates_empty_nlp_is_noop():
    nlp = ResumeNlpEnrichment()
    merged = merge_skill_candidates(["Python", "SQL"], nlp, max_total=80)
    assert merged == ["Python", "SQL"]


def test_merge_skill_candidates_dedupes_case_insensitive():
    nlp = ResumeNlpEnrichment(skill_like_chunks=["react", "Docker"])
    merged = merge_skill_candidates(["Python", "react"], nlp, max_total=80)
    assert "Python" in merged
    assert "Docker" in merged
    assert sum(1 for x in merged if x.lower() == "react") == 1
