"""
Merge activity notifications with direct messages and per-user read state for the Inbox API.

- All system notifications (jobs, clients, candidates, rankings, etc.) appear under **alerts**
  (and **all**).
- User messages use **chat_scope** (general | candidates | clients); the inbox UI only exposes a **candidates** scoped tab (plus **all** / **alerts**). Client-scoped DMs still appear under **all**.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from api.config import get_settings
from api.models import Candidate, Client, InboxMessage, InboxReadState, User
from api.services.activity_feed import build_activity_notifications
from api.services.workspace_scope import ensure_workspace_for_recruiter

_log = logging.getLogger("rezume.api")

_ALLOWED_SCOPES = frozenset({"general", "candidates", "clients"})


def _iso(dt: datetime | None) -> str:
    """UTC instant with explicit Z for correct client parsing."""
    if dt is None:
        t = datetime.utcnow()
        return t.isoformat() + "Z"
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc.isoformat() + "Z"


def inbox_message_preview(subject: str, body: str, max_len: int = 200) -> str:
    subj = (subject or "").strip()
    raw = (body or "").strip()
    if subj and raw:
        line = f"{subj}: {raw}"
    elif subj:
        line = subj
    else:
        line = raw
    if len(line) > max_len:
        return line[: max_len - 1] + "…"
    return line or "(empty message)"


def normalize_chat_scope(raw: str | None) -> str:
    s = (raw or "general").strip().lower()
    return s if s in _ALLOWED_SCOPES else "general"


def tab_matches_item(tab: str, item: dict[str, Any]) -> bool:
    t = (tab or "all").strip().lower()
    if t == "all":
        return True
    if t == "alerts":
        return not item.get("direct")
    if t == "candidates":
        return bool(item.get("direct")) and item.get("chat_scope") == "candidates"
    return False


def resolve_peer_display_path(db: Session, peer_email: str, scope: str) -> tuple[str, str | None]:
    """
    Display name for DM list / previews, and SPA path to open client or candidate profile when known.
    """
    email_key = (peer_email or "").strip().lower()
    if not email_key:
        return "Unknown", None
    sc = normalize_chat_scope(scope)
    if sc == "clients":
        row = (
            db.query(Client)
            .filter(func.lower(Client.email) == email_key)
            .order_by(Client.created_at.asc())
            .first()
        )
        if row:
            name = (row.name or "").strip() or (row.company_name or "").strip() or email_key
            return name, f"/clients/{row.id}"
    elif sc == "candidates":
        row = (
            db.query(Candidate)
            .filter(func.lower(Candidate.contact_email) == email_key)
            .order_by(Candidate.created_at.asc())
            .first()
        )
        if row:
            name = (row.full_name or "").strip() or (row.title or "").strip() or (row.external_id or "").strip() or email_key
            return name, f"/candidates/{row.id}"
    u = db.query(User).filter(func.lower(User.email) == email_key).first()
    if u:
        fn = (u.full_name or "").strip()
        if fn:
            return fn, None
    return peer_email.strip() if peer_email.strip() else email_key, None


def build_inbox_rows(db: Session, user: User, activity_limit: int = 80, message_limit: int = 60) -> list[dict[str, Any]]:
    settings = get_settings()
    role = (getattr(user, "account_role", None) or "recruiter").strip().lower()
    if role == "candidate":
        activity: list[dict[str, Any]] = []
    elif settings.require_auth:
        wid = ensure_workspace_for_recruiter(db, user)
        activity = build_activity_notifications(db, limit=activity_limit, recruiter_workspace_id=wid)
    else:
        activity = build_activity_notifications(db, limit=activity_limit, recruiter_workspace_id=None)
    keys = [str(x["id"]) for x in activity]
    read_set: set[str] = set()
    if keys:
        try:
            rows = (
                db.query(InboxReadState.item_key)
                .filter(InboxReadState.user_id == user.id, InboxReadState.item_key.in_(keys))
                .all()
            )
            read_set = {r[0] for r in rows}
        except Exception as e:
            _log.debug("inbox read states query skipped: %s", e)

    peer_cache: dict[tuple[str, str], tuple[str, str | None]] = {}

    def _peer(peer_em: str, scope: str) -> tuple[str, str | None]:
        key = (peer_em.strip().lower(), normalize_chat_scope(scope))
        if key not in peer_cache:
            peer_cache[key] = resolve_peer_display_path(db, peer_em, scope)
        return peer_cache[key]

    merged: list[dict[str, Any]] = []
    for row in activity:
        iid = str(row["id"])
        merged.append(
            {
                "id": iid,
                "kind": row.get("kind") or "info",
                "message": row.get("message") or "",
                "at": row.get("at") or _iso(None),
                "href": row.get("href"),
                "read": iid in read_set,
                "tabs": ["alerts"],
                "direct": False,
                "sender_email": None,
                "direction": None,
                "peer_email": None,
                "chat_scope": None,
                "peer_display_name": None,
                "peer_profile_path": None,
            }
        )

    try:
        incoming = (
            db.query(InboxMessage, User.email)
            .join(User, User.id == InboxMessage.sender_id)
            .filter(
                InboxMessage.recipient_id == user.id,
                InboxMessage.hidden_for_recipient.is_(False),
            )
            .order_by(InboxMessage.created_at.desc())
            .limit(message_limit)
            .all()
        )
        outgoing = (
            db.query(InboxMessage, User.email)
            .join(User, User.id == InboxMessage.recipient_id)
            .filter(InboxMessage.sender_id == user.id, InboxMessage.hidden_for_sender.is_(False))
            .order_by(InboxMessage.created_at.desc())
            .limit(message_limit)
            .all()
        )
        for m, sender_email in incoming:
            scope = normalize_chat_scope(getattr(m, "chat_scope", None))
            preview = inbox_message_preview(m.subject, m.body)
            display, path = _peer(sender_email, scope)
            merged.append(
                {
                    "id": f"msg-{m.id}",
                    "kind": "message",
                    "message": f"New message from {display} — {preview}",
                    "at": _iso(m.created_at),
                    "href": None,
                    "read": m.read_at is not None,
                    "tabs": [],
                    "direct": True,
                    "sender_email": sender_email,
                    "direction": "in",
                    "peer_email": sender_email,
                    "chat_scope": scope,
                    "peer_display_name": display,
                    "peer_profile_path": path,
                }
            )
        for m, recipient_email in outgoing:
            scope = normalize_chat_scope(getattr(m, "chat_scope", None))
            preview = inbox_message_preview(m.subject, m.body)
            display, path = _peer(recipient_email, scope)
            merged.append(
                {
                    "id": f"msg-{m.id}",
                    "kind": "message",
                    "message": f"Message to {display} — {preview}",
                    "at": _iso(m.created_at),
                    "href": None,
                    "read": True,
                    "tabs": [],
                    "direct": True,
                    "sender_email": None,
                    "direction": "out",
                    "peer_email": recipient_email,
                    "chat_scope": scope,
                    "peer_display_name": display,
                    "peer_profile_path": path,
                }
            )
    except Exception as e:
        _log.debug("inbox messages query skipped: %s", e)

    def _parse_at(s: str) -> datetime:
        try:
            t = str(s).replace("Z", "+00:00")
            return datetime.fromisoformat(t)
        except ValueError:
            return datetime.min

    merged.sort(key=lambda x: _parse_at(str(x["at"])), reverse=True)
    return merged


def mark_inbox_items_read(db: Session, user: User, ids: list[str]) -> None:
    now = datetime.utcnow()
    for raw in ids:
        s = (raw or "").strip()
        if not s:
            continue
        if s.startswith("msg-"):
            try:
                mid = UUID(s.removeprefix("msg-"))
            except ValueError:
                continue
            m = (
                db.query(InboxMessage)
                .filter(
                    InboxMessage.id == mid,
                    InboxMessage.recipient_id == user.id,
                    InboxMessage.hidden_for_recipient.is_(False),
                )
                .first()
            )
            if m:
                m.read_at = now
            continue
        ex = (
            db.query(InboxReadState)
            .filter(InboxReadState.user_id == user.id, InboxReadState.item_key == s)
            .first()
        )
        if not ex:
            db.add(InboxReadState(user_id=user.id, item_key=s, read_at=now))
    db.commit()


def mark_inbox_items_unread(db: Session, user: User, ids: list[str]) -> None:
    msg_ids: list[UUID] = []
    keys: list[str] = []
    for raw in ids:
        s = (raw or "").strip()
        if not s:
            continue
        if s.startswith("msg-"):
            try:
                msg_ids.append(UUID(s.removeprefix("msg-")))
            except ValueError:
                pass
        else:
            keys.append(s)
    if msg_ids:
        for m in (
            db.query(InboxMessage)
            .filter(
                InboxMessage.recipient_id == user.id,
                InboxMessage.id.in_(msg_ids),
                InboxMessage.hidden_for_recipient.is_(False),
            )
            .all()
        ):
            m.read_at = None
    if keys:
        db.query(InboxReadState).filter(InboxReadState.user_id == user.id, InboxReadState.item_key.in_(keys)).delete(
            synchronize_session=False
        )
    db.commit()


def mark_all_inbox_read_for_tab(db: Session, user: User, tab: str) -> int:
    rows = build_inbox_rows(db, user)
    n = 0
    to_mark: list[str] = []
    for it in rows:
        if not tab_matches_item(tab, it):
            continue
        if it.get("direction") == "out":
            continue
        if not it.get("read"):
            to_mark.append(str(it["id"]))
            n += 1
    if to_mark:
        mark_inbox_items_read(db, user, to_mark)
    return n


def mark_all_inbox_unread_for_tab(db: Session, user: User, tab: str) -> int:
    rows = build_inbox_rows(db, user)
    n = 0
    to_mark: list[str] = []
    for it in rows:
        if not tab_matches_item(tab, it):
            continue
        if it.get("direction") == "out":
            continue
        if it.get("read"):
            to_mark.append(str(it["id"]))
            n += 1
    if to_mark:
        mark_inbox_items_unread(db, user, to_mark)
    return n


def parse_inbox_message_uuid(raw: str) -> UUID:
    s = (raw or "").strip()
    if s.startswith("msg-"):
        s = s[4:]
    return UUID(s)


def apply_inbox_message_delete(db: Session, user: User, message_id: UUID, mode: str) -> tuple[bool, str | None]:
    """
    mode ``everyone``: remove the row (sender only — unsend for both parties).
    mode ``me``: hide for the current user only; if both parties hid, the row is removed.

    Returns (ok, err) where err is one of ``not_found``, ``forbidden``, ``bad_mode``.
    """
    raw = (mode or "").strip().lower()
    if raw not in ("everyone", "me"):
        return False, "bad_mode"
    m = (
        db.query(InboxMessage)
        .filter(
            InboxMessage.id == message_id,
            or_(InboxMessage.sender_id == user.id, InboxMessage.recipient_id == user.id),
        )
        .first()
    )
    if not m:
        return False, "not_found"
    if raw == "everyone":
        if m.sender_id != user.id:
            return False, "forbidden"
        db.delete(m)
        db.commit()
        return True, None
    if m.sender_id == user.id:
        m.hidden_for_sender = True
    else:
        m.hidden_for_recipient = True
    if m.hidden_for_sender and m.hidden_for_recipient:
        db.delete(m)
    db.commit()
    return True, None


def delete_inbox_thread_for_user(db: Session, user: User, peer_email: str, scope: str) -> int:
    sc = normalize_chat_scope(scope)
    peer = db.query(User).filter(func.lower(User.email) == peer_email.strip().lower()).first()
    if not peer:
        return 0
    n = (
        db.query(InboxMessage)
        .filter(
            InboxMessage.chat_scope == sc,
            or_(
                and_(InboxMessage.sender_id == user.id, InboxMessage.recipient_id == peer.id),
                and_(InboxMessage.sender_id == peer.id, InboxMessage.recipient_id == user.id),
            ),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(n or 0)
