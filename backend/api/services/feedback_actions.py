"""Map human ranking feedback labels to Candidate.status (global hiring signal)."""


def feedback_action_to_candidate_status(action: str) -> str:
    a = (action or "").strip().lower()
    if a in ("not_a_fit", "not a fit", "reject"):
        a = "rejected"
    if a in ("selected", "shortlisted", "rejected"):
        return a
    out = "".join(c if c.isalnum() or c in "-_" else "_" for c in a).strip("_")
    return (out[:64] or "reviewed") if out else "new"
