from __future__ import annotations

from sqlalchemy.orm import Session

from api.models import ActivityEvent


def log_activity(db: Session, *, kind: str, message: str, href: str = "") -> None:
    """
    Best-effort append-only activity logging.
    Never throws (notifications should not break core flows).
    """
    try:
        ev = ActivityEvent(kind=(kind or "info")[:64], message=(message or "")[:512], href=(href or "")[:256])
        db.add(ev)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
