"""Shared FastAPI dependencies (auth)."""
from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.models import User
from api.security import decode_token

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
    user: Annotated[Optional[User], Depends(get_current_user_optional)],
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
