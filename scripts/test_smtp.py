#!/usr/bin/env python3
"""
Send one test email using the same SMTP settings as the API (.env at repo root).

Run from repository root:
  PYTHONPATH=backend python scripts/test_smtp.py

If this prints OK but the app still does not mail, the API process is probably not
loading the same .env (wrong cwd) or needs a full restart.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(ROOT)

from api.config import get_settings  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    cfg = get_settings()
    if not (cfg.smtp_host or "").strip():
        print("ERROR: SMTP_HOST is empty in loaded settings. Run from repo root so .env is found.")
        sys.exit(1)
    user = (cfg.smtp_user or "").strip()
    if not user:
        print("ERROR: SMTP_USER is empty.")
        sys.exit(1)
    import smtplib  # noqa: E402
    import ssl  # noqa: E402
    from email.message import EmailMessage  # noqa: E402

    host = cfg.smtp_host.strip()
    port = int(cfg.smtp_port or 587)
    pw = (cfg.smtp_password or "").strip()
    mail_from = (cfg.smtp_from or "").strip() or user
    ctx = ssl.create_default_context()
    em = EmailMessage()
    em["Subject"] = "Rezume AI — SMTP test"
    em["From"] = mail_from
    em["To"] = user
    em.set_content(
        "This is a manual SMTP test from scripts/test_smtp.py.\n"
        "If you received it, Gmail + .env are correct; restart the API and try register/forgot-password again.\n"
    )
    print(f"Connecting {host}:{port} ssl={getattr(cfg, 'smtp_ssl', False)} tls={cfg.smtp_use_tls} ...")
    try:
        if getattr(cfg, "smtp_ssl", False):
            with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as s:
                s.login(user, pw)
                s.send_message(em)
        elif cfg.smtp_use_tls:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(user, pw)
                s.send_message(em)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                s.login(user, pw)
                s.send_message(em)
    except Exception as e:
        print("FAILED:", type(e).__name__, e)
        sys.exit(2)
    print("OK: message sent to", user, "- check Inbox and Spam.")


if __name__ == "__main__":
    main()
