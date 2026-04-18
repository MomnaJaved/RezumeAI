"""Optional JWT auth: email verification + login."""
import logging
import re
import secrets
import smtplib
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.models import User
from api.schemas import (
    ChangePasswordIn,
    RegisterStartResponse,
    TokenResponse,
    UserProfileOut,
    UserProfileUpdate,
    UserRegisterIn,
    VerifyEmailCodeIn,
    VerifyEmailCodeResponse,
)
from api.security import create_access_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
_log = logging.getLogger("rezume.api")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _send_verification_email(to_email: str, code: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        if settings.dev_email_print_code:
            _log.warning("DEV EMAIL MODE: verification code for %s is %s", to_email, code)
            return
        raise RuntimeError("SMTP is not configured")

    subject = "Rezume AI — verify your email"
    body = (
        "Your Rezume AI verification code is:\n\n"
        f"{code}\n\n"
        f"This code expires in {settings.verification_code_ttl_minutes} minutes.\n"
    )
    msg = (
        f"From: {settings.smtp_from}\r\n"
        f"To: {to_email}\r\n"
        f"Subject: {subject}\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}"
    )

    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.sendmail(settings.smtp_from, [to_email], msg.encode("utf-8"))
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.ehlo()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.sendmail(settings.smtp_from, [to_email], msg.encode("utf-8"))


@router.post("/register-start", response_model=RegisterStartResponse)
def register_start(body: UserRegisterIn, db: Session = Depends(get_db)):
    settings = get_settings()
    email = body.email.strip().lower()
    if not RE_EMAIL.match(email):
        raise HTTPException(status_code=400, detail="Invalid email")

    existing = db.query(User).filter(User.email == email).first()
    if existing and getattr(existing, "is_verified", False):
        raise HTTPException(status_code=409, detail="Email already registered")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = datetime.utcnow() + timedelta(minutes=settings.verification_code_ttl_minutes)

    if existing:
        existing.password_hash = hash_password(body.password)
        existing.verification_code_hash = hash_password(code)
        existing.verification_code_expires_at = expires
        existing.is_verified = False
        user = existing
    else:
        user = User(
            email=email,
            password_hash=hash_password(body.password),
            is_verified=False,
            verification_code_hash=hash_password(code),
            verification_code_expires_at=expires,
        )
        db.add(user)

    try:
        _send_verification_email(email, code)
    except Exception as e:
        _log.warning("Verification email send failed to %s: %s", email, e)
        raise HTTPException(status_code=503, detail="Could not send verification email. Try again later.") from e

    db.commit()
    _log.info("Started registration for %s", email)
    return RegisterStartResponse(status="code_sent")


@router.post("/verify-email", response_model=VerifyEmailCodeResponse)
def verify_email(body: VerifyEmailCodeIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    if getattr(user, "is_verified", False):
        return VerifyEmailCodeResponse(status="verified")

    if not getattr(user, "verification_code_hash", "") or not getattr(user, "verification_code_expires_at", None):
        raise HTTPException(status_code=400, detail="No active verification code. Please register again.")
    if datetime.utcnow() > user.verification_code_expires_at:
        raise HTTPException(status_code=400, detail="Verification code expired. Please register again.")
    if not verify_password(body.code, user.verification_code_hash):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    user.is_verified = True
    user.verification_code_hash = ""
    user.verification_code_expires_at = None
    db.commit()
    _log.info("Verified user %s", email)
    return VerifyEmailCodeResponse(status="verified")


@router.post("/login", response_model=TokenResponse)
def login(body: UserRegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not getattr(user, "is_verified", True):
        raise HTTPException(status_code=403, detail="Email not verified")
    token = create_access_token(str(user.id), extra={"email": email})
    return TokenResponse(access_token=token)


def _get_auth_user(request: Request, db: Session) -> User:
    """Extract and validate JWT from Authorization header, return User or raise 401."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        uid = UUID(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _profile_out(u: User) -> UserProfileOut:
    return UserProfileOut(
        id=str(u.id),
        email=u.email,
        full_name=getattr(u, "full_name", "") or "",
        phone=getattr(u, "phone", "") or "",
        address=getattr(u, "address", "") or "",
        company=getattr(u, "company", "") or "",
        available_hours=getattr(u, "available_hours", "") or "",
        role_label=getattr(u, "role_label", "Recruiter") or "Recruiter",
        avatar_data=getattr(u, "avatar_data", None),
    )


@router.get("/me", response_model=UserProfileOut)
def get_me(request: Request, db: Session = Depends(get_db)):
    return _profile_out(_get_auth_user(request, db))


@router.patch("/me", response_model=UserProfileOut)
def update_me(request: Request, body: UserProfileUpdate, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    for field, val in body.model_dump(exclude_unset=True).items():
        if val is not None:
            setattr(u, field, val)
    db.commit()
    db.refresh(u)
    return _profile_out(u)


@router.post("/change-password")
def change_password(request: Request, body: ChangePasswordIn, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    if not verify_password(body.current_password, u.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    u.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "password_changed"}
