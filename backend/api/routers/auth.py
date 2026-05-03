"""Optional JWT auth: email verification + login."""
from __future__ import annotations

import logging
import re
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.models import ActivityEvent, Candidate, LoginOtpChallenge, User, UserSession
from api.schemas import (
    ChangePasswordIn,
    DeleteAccountIn,
    ForgotPasswordIn,
    ForgotPasswordResponse,
    LoginCredentialsIn,
    LoginOtpCompleteIn,
    LoginResult,
    RegisterStartResponse,
    ResetPasswordIn,
    ResetPasswordResponse,
    TokenResponse,
    UserProfileOut,
    UserProfileUpdate,
    UserRegisterIn,
    UserSessionOut,
    VerifyEmailCodeIn,
    VerifyEmailCodeResponse,
)
from api.security import create_access_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
_log = logging.getLogger("rezume.api")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _smtp_deliver(to_email: str, subject: str, body_plain: str) -> None:
    """
    Send one plain-text email. Uses ssl.create_default_context() for STARTTLS (macOS/LibreSSL + Gmail).
    """
    settings = get_settings()
    host = (settings.smtp_host or "").strip()
    if not host:
        return
    user = (settings.smtp_user or "").strip()
    password = (settings.smtp_password or "").strip()
    mail_from = (settings.smtp_from or "").strip() or user
    port = int(settings.smtp_port or 587)
    ctx = ssl.create_default_context()
    use_ssl = getattr(settings, "smtp_ssl", False)

    _log.info(
        "SMTP send start to=%r host=%r port=%s ssl=%s starttls=%s from=%r",
        to_email,
        host,
        port,
        use_ssl,
        settings.smtp_use_tls,
        mail_from,
    )

    em = EmailMessage()
    em["Subject"] = subject
    em["From"] = mail_from
    em["To"] = to_email
    em.set_content(body_plain)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as s:
                if getattr(settings, "smtp_debug", False):
                    s.set_debuglevel(1)
                if user:
                    s.login(user, password)
                s.send_message(em)
        elif settings.smtp_use_tls:
            with smtplib.SMTP(host, port, timeout=30) as s:
                if getattr(settings, "smtp_debug", False):
                    s.set_debuglevel(1)
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                if user:
                    s.login(user, password)
                s.send_message(em)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                if getattr(settings, "smtp_debug", False):
                    s.set_debuglevel(1)
                s.ehlo()
                if user:
                    s.login(user, password)
                s.send_message(em)
    except Exception:
        _log.exception(
            "SMTP send failed to=%r host=%r port=%s ssl=%s starttls=%s",
            to_email,
            host,
            port,
            use_ssl,
            settings.smtp_use_tls,
        )
        raise

    _log.info("SMTP delivered subject=%r to=%r", subject, to_email)


def _send_verification_email(to_email: str, code: str) -> None:
    settings = get_settings()
    if not (settings.smtp_host or "").strip():
        _log.warning(
            "No SMTP_HOST: verification code for %s is %s (check the API terminal; set SMTP_HOST to send email.)",
            to_email,
            code,
        )
        return
    if settings.dev_email_print_code:
        _log.warning("DEV_EMAIL_PRINT_CODE: verification code for %s is %s", to_email, code)

    subject = "Rezume AI — verify your email"
    body = (
        "Your Rezume AI verification code is:\n\n"
        f"{code}\n\n"
        f"This code expires in {settings.verification_code_ttl_minutes} minutes.\n"
    )
    _smtp_deliver(to_email, subject, body)


def _send_login_otp_email(to_email: str, code: str) -> None:
    settings = get_settings()
    if not (settings.smtp_host or "").strip():
        _log.warning(
            "No SMTP_HOST: sign-in code for %s is %s (check the API terminal; set SMTP_HOST to send email.)",
            to_email,
            code,
        )
        return
    if settings.dev_email_print_code:
        _log.warning("DEV_EMAIL_PRINT_CODE: login code for %s is %s", to_email, code)

    subject = "Rezume AI — sign-in verification code"
    body = (
        "Your Rezume AI sign-in code is:\n\n"
        f"{code}\n\n"
        f"This code expires in {settings.verification_code_ttl_minutes} minutes.\n"
        "If you did not try to sign in, ignore this email.\n"
    )
    _smtp_deliver(to_email, subject, body)


def _send_password_reset_email(to_email: str, code: str) -> None:
    settings = get_settings()
    if not (settings.smtp_host or "").strip():
        _log.warning(
            "No SMTP_HOST: password reset code for %s is %s (check the API terminal; set SMTP_HOST to send email.)",
            to_email,
            code,
        )
        return
    if settings.dev_email_print_code:
        _log.warning("DEV_EMAIL_PRINT_CODE: password reset code for %s is %s", to_email, code)

    subject = "Rezume AI — reset your password"
    body = (
        "We received a request to reset your Rezume AI password.\n\n"
        f"Your reset code is:\n\n{code}\n\n"
        f"This code expires in {settings.verification_code_ttl_minutes} minutes.\n"
        "If you did not request this, you can ignore this email.\n"
    )
    _smtp_deliver(to_email, subject, body)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return (request.client.host or "")[:64]
    return ""


def _device_label(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "edg/" in ua or "edgios" in ua or " edg" in ua:
        browser = "Edge"
    elif "chrome" in ua and "chromium" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    if "windows" in ua:
        os_ = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        os_ = "macOS"
    elif "android" in ua:
        os_ = "Android"
    elif "linux" in ua:
        os_ = "Linux"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        os_ = "iOS"
    else:
        os_ = "Unknown OS"
    return f"{browser} · {os_}"


def _bearer_payload(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        return None
    return decode_token(token)


def _norm_account_role(raw: object) -> str:
    s = (str(raw or "recruiter")).strip().lower()
    return s if s in ("recruiter", "candidate") else "recruiter"


def _issue_token_with_session(db: Session, user: User, request: Request) -> str:
    jti = secrets.token_urlsafe(32)
    ar = _norm_account_role(getattr(user, "account_role", None))
    token = create_access_token(str(user.id), extra={"email": user.email, "jti": jti, "account_role": ar})
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")
    label = _device_label(ua)[:250]
    loc = f"Network · {ip}" if ip else "Unknown location"
    row = UserSession(
        user_id=user.id,
        jti=jti,
        device_label=label,
        ip_address=ip,
        location_label=loc[:250],
    )
    db.add(row)
    db.commit()
    return token


@router.post("/register-start", response_model=RegisterStartResponse)
def register_start(body: UserRegisterIn, db: Session = Depends(get_db)):
    settings = get_settings()
    email = body.email.strip().lower()
    if not RE_EMAIL.match(email):
        raise HTTPException(status_code=400, detail="Invalid email")
    raw_ar = (getattr(body, "account_role", None) or "recruiter").strip().lower()
    if raw_ar not in ("recruiter", "candidate"):
        raise HTTPException(status_code=422, detail="account_role must be recruiter or candidate")
    ar = raw_ar

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
        existing.account_role = ar
        user = existing
    else:
        user = User(
            email=email,
            password_hash=hash_password(body.password),
            is_verified=False,
            verification_code_hash=hash_password(code),
            verification_code_expires_at=expires,
            account_role=ar,
        )
        db.add(user)

    try:
        _send_verification_email(email, code)
    except Exception as e:
        _log.warning("Verification email send failed to %s: %s", email, e)
        _log.warning(
            "Verification code for %s is %s (stored; use verify-email or check SMTP settings.)",
            email,
            code,
        )

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


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not RE_EMAIL.match(email):
        return ForgotPasswordResponse()
    user = db.query(User).filter(User.email == email).first()
    # Any existing account may reset; login still requires verified email until they complete verify-email.
    if not user:
        return ForgotPasswordResponse()
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = datetime.utcnow() + timedelta(minutes=get_settings().verification_code_ttl_minutes)
    user.password_reset_code_hash = hash_password(code)
    user.password_reset_expires_at = expires
    try:
        _send_password_reset_email(email, code)
    except Exception as e:
        _log.warning("Password reset email failed for %s: %s", email, e)
        _log.warning(
            "Password reset code for %s is %s (stored; use forgot-password step 2 or fix SMTP.)",
            email,
            code,
        )
    db.commit()
    _log.info("Password reset token saved for %s", email)
    return ForgotPasswordResponse()


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")
    ph = getattr(user, "password_reset_code_hash", "") or ""
    exp = getattr(user, "password_reset_expires_at", None)
    if not ph or not exp or datetime.utcnow() > exp:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")
    if not verify_password(body.code.strip(), ph):
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")
    user.password_hash = hash_password(body.new_password)
    user.password_reset_code_hash = ""
    user.password_reset_expires_at = None
    db.query(UserSession).filter(UserSession.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    _log.info("Password reset completed for %s", email)
    return ResetPasswordResponse()


@router.post("/login", response_model=LoginResult)
def login(request: Request, body: LoginCredentialsIn, db: Session = Depends(get_db)):
    settings = get_settings()
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="No account found for this email")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")
    if not getattr(user, "is_verified", True):
        raise HTTPException(status_code=403, detail="Email not verified")
    if getattr(user, "two_factor_enabled", False):
        db.query(LoginOtpChallenge).filter(LoginOtpChallenge.user_id == user.id).delete(synchronize_session=False)
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires = datetime.utcnow() + timedelta(minutes=settings.verification_code_ttl_minutes)
        ch = LoginOtpChallenge(user_id=user.id, code_hash=hash_password(code), expires_at=expires)
        db.add(ch)
        db.flush()
        try:
            _send_login_otp_email(email, code)
        except Exception as e:
            _log.warning("Login OTP email failed for %s: %s", email, e)
            _log.warning(
                "Sign-in OTP for %s is %s (challenge saved; enter in app or fix SMTP.)",
                email,
                code,
            )
        db.commit()
        db.refresh(ch)
        return LoginResult(requires_otp=True, otp_challenge_id=str(ch.id))
    token = _issue_token_with_session(db, user, request)
    return LoginResult(access_token=token, account_role=_norm_account_role(getattr(user, "account_role", None)))


@router.post("/login-otp", response_model=TokenResponse)
def login_otp(request: Request, body: LoginOtpCompleteIn, db: Session = Depends(get_db)):
    try:
        cid = UUID(body.challenge_id.strip())
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid challenge")
    ch = db.query(LoginOtpChallenge).filter(LoginOtpChallenge.id == cid).first()
    if not ch:
        raise HTTPException(status_code=400, detail="Invalid or expired challenge")
    if datetime.utcnow() > ch.expires_at:
        db.delete(ch)
        db.commit()
        raise HTTPException(status_code=400, detail="Code expired. Sign in again.")
    if not verify_password(body.code.strip(), ch.code_hash):
        raise HTTPException(status_code=400, detail="Invalid code")
    user = db.query(User).filter(User.id == ch.user_id).first()
    if not user:
        db.delete(ch)
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid challenge")
    db.delete(ch)
    db.commit()
    token = _issue_token_with_session(db, user, request)
    return TokenResponse(access_token=token, account_role=_norm_account_role(getattr(user, "account_role", None)))


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
    jti = payload.get("jti")
    if jti:
        sess = db.query(UserSession).filter(UserSession.jti == jti, UserSession.user_id == uid).first()
        if not sess:
            raise HTTPException(status_code=401, detail="Session expired or signed out elsewhere")
        sess.last_seen_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            db.rollback()
    return user


def _profile_out(u: User, db: Session | None = None) -> UserProfileOut:
    ws: str | None = None
    if db is not None and _norm_account_role(getattr(u, "account_role", None)) != "candidate":
        from api.services.workspace_scope import ensure_workspace_for_recruiter

        w = ensure_workspace_for_recruiter(db, u)
        ws = str(w) if w else None
    elif getattr(u, "workspace_id", None) is not None:
        ws = str(u.workspace_id)
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
        two_factor_enabled=bool(getattr(u, "two_factor_enabled", False)),
        account_role=_norm_account_role(getattr(u, "account_role", None)),
        workspace_id=ws,
    )


@router.get("/me", response_model=UserProfileOut)
def get_me(request: Request, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    return _profile_out(u, db)


@router.patch("/me", response_model=UserProfileOut)
def update_me(request: Request, body: UserProfileUpdate, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    for field, val in body.model_dump(exclude_unset=True).items():
        if val is not None:
            setattr(u, field, val)
    db.commit()
    db.refresh(u)
    return _profile_out(u, db)


@router.post("/delete-account")
def delete_account(request: Request, body: DeleteAccountIn, db: Session = Depends(get_db)):
    """
    Permanently delete the authenticated user.

    **Candidate accounts:** the linked pool ``Candidate`` row (if any) is **hard-deleted**
    first so rankings, applications, and profile data disappear for all recruiters globally.
    Per-user ``ActivityEvent`` rows for that account are removed. Then the ``User`` row is
    deleted (sessions, inbox messages, etc. cascade as configured).

    **Recruiter accounts:** jobs keep ``created_by_user_id`` cleared via FK; uploaded
    ``Candidate`` rows are only unlinked where ``user_id`` pointed at this user (SET NULL).
    """
    u = _get_auth_user(request, db)
    if not verify_password(body.password, u.password_hash):
        raise HTTPException(status_code=400, detail="Password is incorrect")
    email = u.email
    uid = u.id
    role = _norm_account_role(getattr(u, "account_role", None))
    if role == "candidate":
        pool = db.query(Candidate).filter(Candidate.user_id == uid).first()
        if pool is not None:
            db.delete(pool)
        db.query(ActivityEvent).filter(ActivityEvent.user_id == uid).delete(synchronize_session=False)
    db.delete(u)
    db.commit()
    _log.info("User deleted account email=%s id=%s role=%s", email, uid, role)
    return {"status": "deleted"}


@router.post("/change-password")
def change_password(request: Request, body: ChangePasswordIn, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    if not verify_password(body.current_password, u.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    payload = _bearer_payload(request) or {}
    current_jti = payload.get("jti")
    u.password_hash = hash_password(body.new_password)
    q = db.query(UserSession).filter(UserSession.user_id == u.id)
    if current_jti:
        q = q.filter(UserSession.jti != current_jti)
    q.delete(synchronize_session=False)
    db.commit()
    return {"status": "password_changed"}


@router.get("/sessions", response_model=list[UserSessionOut])
def list_sessions(request: Request, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    payload = _bearer_payload(request) or {}
    current_jti = payload.get("jti")
    rows = (
        db.query(UserSession)
        .filter(UserSession.user_id == u.id)
        .order_by(UserSession.last_seen_at.desc())
        .all()
    )
    out: list[UserSessionOut] = []
    for r in rows:
        out.append(
            UserSessionOut(
                id=str(r.id),
                device_label=(r.device_label or "Unknown device")[:250],
                location_label=(r.location_label or "")[:250],
                ip_address=(r.ip_address or "")[:64],
                created_at=r.created_at.isoformat() if r.created_at else "",
                last_seen_at=r.last_seen_at.isoformat() if r.last_seen_at else "",
                is_current=bool(current_jti and r.jti == current_jti),
            )
        )
    return out


@router.delete("/sessions/{session_id}", status_code=204)
def delete_one_session(session_id: str, request: Request, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    try:
        sid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session id")
    sess = db.query(UserSession).filter(UserSession.id == sid, UserSession.user_id == u.id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(sess)
    db.commit()
    return Response(status_code=204)


@router.delete("/sessions", status_code=204)
def delete_all_sessions(request: Request, db: Session = Depends(get_db)):
    u = _get_auth_user(request, db)
    db.query(UserSession).filter(UserSession.user_id == u.id).delete(synchronize_session=False)
    db.commit()
    return Response(status_code=204)
