from __future__ import annotations

from api.services.feedback_actions import feedback_action_to_candidate_status


def test_maps_core_actions():
    assert feedback_action_to_candidate_status("selected") == "selected"
    assert feedback_action_to_candidate_status("SHORTLISTED") == "shortlisted"
    assert feedback_action_to_candidate_status("rejected") == "rejected"


def test_maps_aliases_to_rejected():
    assert feedback_action_to_candidate_status("not_a_fit") == "rejected"
    assert feedback_action_to_candidate_status("reject") == "rejected"
