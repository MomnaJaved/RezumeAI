"""Shared FastAPI dependencies (auth)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.models import User
from api.security import decode_token
from api.services.workspace_scope import workspace_id_for_recruiter_user

_bearer = HTTPBearer(auto_error=False)


def get_current_user_optional(
    db: Session = Depends(get_db),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[User]:
    if creds is None or not creds.credentials:
        return None
    payload = decode_token(creds.credentials)
    if not payload or "sub" not in payload:
        return None
    try:
        uid = UUID(payload["sub"])
    except (ValueError, TypeError):
        return None
    return db.query(User).filter(User.id == uid).first()


def require_user_if_auth_enabled(
    user: Optional[User] = Depends(get_current_user_optional),
) -> Optional[User]:
    settings = get_settings()
    if not settings.require_auth:
        return None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def recruiter_meta_scope(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Optional[UUID]:
    """
    Resolve the workspace id for dashboard / analytics aggregates.

    - Authenticated recruiter: always scope to their workspace, regardless of
      ``REQUIRE_AUTH``. This matches the behaviour of the candidates/jobs
      routers and prevents a fresh account from seeing data that belongs to
      other tenants in the shared database.
    - No user with ``REQUIRE_AUTH=true``: 401 (protected deployment).
    - No user with ``REQUIRE_AUTH=false``: return None so legacy/anonymous
      clients (e.g. unit tests, older scripts) still get global counts.
    - Candidate account: 403 — these endpoints are recruiter-only.
    """
    settings = get_settings()
    if user is None:
        if settings.require_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None
    role = (getattr(user, "account_role", None) or "recruiter").strip().lower()
    if role == "candidate":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required")
    return workspace_id_for_recruiter_user(db, user)
