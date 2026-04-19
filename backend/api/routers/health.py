from fastapi import APIRouter

from api.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/smtp")
def health_smtp():
    """
    Shows whether the API process loaded SMTP settings (no secrets).
    Open in browser: http://127.0.0.1:8000/health/smtp — if smtp_host_set is false, restart the API from repo root.
    """
    s = get_settings()
    host = (s.smtp_host or "").strip()
    return {
        "smtp_host_set": bool(host),
        "smtp_host": host or None,
        "smtp_port": s.smtp_port,
        "smtp_ssl": getattr(s, "smtp_ssl", False),
        "smtp_use_tls": s.smtp_use_tls,
        "smtp_user_set": bool((s.smtp_user or "").strip()),
        "smtp_password_set": bool((s.smtp_password or "").strip()),
        "smtp_from": (s.smtp_from or "").strip() or None,
    }
