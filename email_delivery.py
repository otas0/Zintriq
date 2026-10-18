"""Transactional email — SMTP when configured, otherwise caller logs the link."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from observability.trace import trace


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip())


def send_transactional_email(
    to: str,
    subject: str,
    text_body: str,
    *,
    html_body: str | None = None,
) -> bool:
    """Send email via SMTP. Returns False when SMTP is not configured."""
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host or not to.strip():
        return False
    if host.lower() in {"console", "log", "-"}:
        import logging

        logging.getLogger("app.mail").info(
            "smtp.console to=%s subject=%s\n%s", to.strip(), subject, text_body
        )
        return True

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", user or "noreply@zintriq.local").strip()
    use_tls = os.environ.get("SMTP_USE_TLS", "1").strip().lower() not in ("0", "false", "no")
    use_ssl = os.environ.get("SMTP_USE_SSL", "").strip().lower() in ("1", "true", "yes")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to.strip()
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    if use_ssl:
        with trace("smtp.send_ssl", host=host, port=port):
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
    else:
        with trace("smtp.send", host=host, port=port):
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                if use_tls:
                    smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
    return True
