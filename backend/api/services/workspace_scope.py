"""Multi-tenant workspace: ensure recruiter workspace and resolve visible candidate IDs."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from api.models import (
    Candidate,
    Job,
    JobApplicant,
    JobCandidateRanking,
    JobShortlistedCandidate,
    RecruiterCandidateHidden,
    User,
    Workspace,
)


def ensure_workspace_for_recruiter(db: Session, user: User) -> UUID | None:
    """
    Recruiters get a dedicated workspace on first use (Manatal-style tenant).
    Candidates never have a workspace_id.
    """
    role = (getattr(user, "account_role", None) or "recruiter").strip().lower()
    if role == "candidate":
        return None
    wid = getattr(user, "workspace_id", None)
    if wid is not None:
        return wid
    label = (user.email or "user").split("@")[0][:48] or "workspace"
    ws = Workspace(name=f"{label} workspace")
    db.add(ws)
    db.flush()
    user.workspace_id = ws.id
    db.commit()
    db.refresh(user)
    return ws.id


def workspace_id_for_recruiter_user(db: Session, user: User) -> UUID:
    """Return workspace id, creating one if missing. Raises if candidate."""
    role = (getattr(user, "account_role", None) or "recruiter").strip().lower()
    if role == "candidate":
        raise ValueError("not a recruiter")
    w = ensure_workspace_for_recruiter(db, user)
    if w is None:
        raise RuntimeError("workspace missing for recruiter")
    return w


def candidate_visibility_predicate(workspace_id: UUID):
    """
    Boolean SQL expression that's true for candidates visible to ``workspace_id``.

    A candidate is visible if *any* of the following hold:
      1. They were uploaded into this workspace (``candidates.workspace_id`` match).
      2. They appear as an applicant / ranking / shortlist row on any job in
         this workspace (legacy data, portal applicants, cross-linked candidates).

    AND the candidate has NOT been soft-deleted by this workspace (no row in
    ``recruiter_candidate_hidden`` for this workspace + candidate pair).
    """
    in_workspace = or_(
        Candidate.workspace_id == workspace_id,
        exists()
        .where(
            JobApplicant.candidate_id == Candidate.id,
            JobApplicant.job_id == Job.id,
            Job.workspace_id == workspace_id,
        ),
        exists()
        .where(
            JobCandidateRanking.candidate_id == Candidate.id,
            JobCandidateRanking.job_id == Job.id,
            Job.workspace_id == workspace_id,
        ),
        exists()
        .where(
            JobShortlistedCandidate.candidate_id == Candidate.id,
            JobShortlistedCandidate.job_id == Job.id,
            Job.workspace_id == workspace_id,
        ),
    )
    not_hidden = ~exists().where(
        RecruiterCandidateHidden.workspace_id == workspace_id,
        RecruiterCandidateHidden.candidate_id == Candidate.id,
    )
    return and_(in_workspace, not_hidden)


def candidate_query_filtered_for_workspace(base_query, workspace_id: UUID):
    """
    Restrict a Candidate query to profiles visible to ``workspace_id``.
    See :func:`candidate_visibility_predicate` for the visibility rules.
    """
    return base_query.filter(candidate_visibility_predicate(workspace_id))


def jobs_in_workspace_query(db: Session, workspace_id: UUID):
    return db.query(Job).filter(Job.workspace_id == workspace_id)
