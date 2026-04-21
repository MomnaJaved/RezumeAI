from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from api.models import ActivityEvent


def log_activity(
    db: Session,
    *,
    kind: str,
    message: str,
    href: str = "",
    workspace_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
) -> None:
    """
    Best-effort append-only activity logging.
    Pass ``workspace_id`` so authenticated recruiters only see their own events.
    Pass ``user_id`` for strict per-user notification isolation per the system spec.
    Never throws (notifications should not break core flows).
    """
    try:
        ev = ActivityEvent(
            kind=(kind or "info")[:64],
            message=(message or "")[:512],
            href=(href or "")[:256],
            workspace_id=workspace_id,
            user_id=user_id,
        )
        db.add(ev)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
