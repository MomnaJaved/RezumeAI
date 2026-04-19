from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import InboxMessage, User
from api.routers.auth import _get_auth_user
from api.schemas import (
    InboxIdsBody,
    InboxItemOut,
    InboxMarkResult,
    InboxMessageDeleteIn,
    InboxSendIn,
    InboxTabBody,
    InboxThreadDeleteIn,
    InboxThreadDeleteResult,
)
from api.services.inbox_feed import (
    apply_inbox_message_delete,
    build_inbox_rows,
    delete_inbox_thread_for_user,
    inbox_message_preview,
    mark_all_inbox_read_for_tab,
    mark_all_inbox_unread_for_tab,
    mark_inbox_items_read,
    mark_inbox_items_unread,
    normalize_chat_scope,
    parse_inbox_message_uuid,
    resolve_peer_display_path,
)

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("", response_model=list[InboxItemOut])
def list_inbox(request: Request, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    rows = build_inbox_rows(db, u)
    return [InboxItemOut.model_validate(x) for x in rows]


@router.post("/mark-read", response_model=InboxMarkResult)
def inbox_mark_read(request: Request, body: InboxIdsBody, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    ids = [x.strip() for x in (body.ids or []) if (x or "").strip()]
    if not ids:
        return InboxMarkResult(updated=0)
    mark_inbox_items_read(db, u, ids)
    return InboxMarkResult(updated=len(ids))


@router.post("/mark-unread", response_model=InboxMarkResult)
def inbox_mark_unread(request: Request, body: InboxIdsBody, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    ids = [x.strip() for x in (body.ids or []) if (x or "").strip()]
    if not ids:
        return InboxMarkResult(updated=0)
    mark_inbox_items_unread(db, u, ids)
    return InboxMarkResult(updated=len(ids))


@router.post("/mark-all-read", response_model=InboxMarkResult)
def inbox_mark_all_read(request: Request, body: InboxTabBody, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    tab = (body.tab or "all").strip().lower()
    if tab not in ("all", "alerts", "candidates"):
        raise HTTPException(status_code=422, detail="tab must be one of: all, alerts, candidates")
    n = mark_all_inbox_read_for_tab(db, u, tab)
    return InboxMarkResult(updated=n)


@router.post("/mark-all-unread", response_model=InboxMarkResult)
def inbox_mark_all_unread(request: Request, body: InboxTabBody, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    tab = (body.tab or "all").strip().lower()
    if tab not in ("all", "alerts", "candidates"):
        raise HTTPException(status_code=422, detail="tab must be one of: all, alerts, candidates")
    n = mark_all_inbox_unread_for_tab(db, u, tab)
    return InboxMarkResult(updated=n)


@router.post("/send", response_model=InboxItemOut, status_code=201)
def inbox_send(request: Request, body: InboxSendIn, db: Session = Depends(get_db)):
    sender = _get_auth_user(request, db)
    email = (body.to_email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=422, detail="to_email is required")
    recipient = db.query(User).filter(func.lower(User.email) == email).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="No Rezume user found with that email")
    if recipient.id == sender.id:
        raise HTTPException(status_code=400, detail="Cannot send a message to yourself")
    subj = (body.subject or "").strip()
    msg_body = (body.body or "").strip()
    scope = normalize_chat_scope(getattr(body, "chat_scope", None))
    m = InboxMessage(
        sender_id=sender.id,
        recipient_id=recipient.id,
        chat_scope=scope,
        subject=subj[:512],
        body=msg_body,
        read_at=None,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    peer = recipient.email
    preview = inbox_message_preview(subj, msg_body)
    display, path = resolve_peer_display_path(db, peer, scope)
    line = f"Message to {display} — {preview}"
    return InboxItemOut(
        id=f"msg-{m.id}",
        kind="message",
        message=line,
        at=_inbox_send_at(m.created_at),
        href=None,
        read=True,
        tabs=[],
        direct=True,
        sender_email=None,
        direction="out",
        peer_email=peer,
        chat_scope=scope,
        peer_display_name=display,
        peer_profile_path=path,
    )


def _inbox_send_at(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc.isoformat() + "Z"


@router.post("/messages/{message_id}/delete", status_code=204)
def inbox_delete_message(request: Request, message_id: str, body: InboxMessageDeleteIn, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    try:
        mid = parse_inbox_message_uuid(message_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid message id") from None
    ok, err = apply_inbox_message_delete(db, u, mid, body.mode)
    if ok:
        return Response(status_code=204)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Message not found") from None
    if err == "forbidden":
        raise HTTPException(status_code=403, detail="Only the sender can delete this message for everyone") from None
    raise HTTPException(status_code=422, detail="mode must be everyone or me") from None


@router.post("/thread/delete", response_model=InboxThreadDeleteResult)
def inbox_delete_thread(request: Request, body: InboxThreadDeleteIn, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    sc = normalize_chat_scope(body.chat_scope)
    n = delete_inbox_thread_for_user(db, u, body.peer_email, sc)
    return InboxThreadDeleteResult(deleted=n)
