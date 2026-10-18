"""Signup lists for download links, platform launch notices, and the hardware waitlist.

Emails live only in this table. Confirmation mail goes through the same SMTP
sender Magic Link / guest remember uses. When SMTP is not configured, callers
hide the form instead of accepting an address they cannot write to.
"""

from __future__ import annotations

import hashlib
import os
import secrets

KINDS = ("download_link", "platform_notify", "hardware_wait")
PLATFORMS = ("mac", "win", "linux")


def mail_configured() -> bool:
    from email_delivery import smtp_configured

    return smtp_configured()


def init_site_notice_tables(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS site_notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE,
            platform TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            region TEXT NOT NULL DEFAULT '',
            token_hash TEXT NOT NULL,
            unsubscribed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(kind, email, platform)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS site_notice_hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )


def _limit() -> int:
    try:
        return max(1, int(os.environ.get("SITE_NOTICE_LIMIT", "5")))
    except ValueError:
        return 5


def _window_minutes() -> int:
    try:
        return max(1, int(os.environ.get("SITE_NOTICE_WINDOW_MINUTES", "15")))
    except ValueError:
        return 15


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _valid_email(email: str) -> bool:
    if not email or len(email) > 200 or "@" not in email:
        return False
    domain = email.split("@", 1)[1]
    return "." in domain and " " not in email


def _messages(kind: str, email: str, platform: str) -> dict[str, str]:
    from i18n_platform import translate as _

    name = {"mac": "macOS", "win": "Windows", "linux": "Linux"}.get(platform, platform)
    if kind == "hardware_wait":
        ok = _("hw.wait.done", email=email)
        already = _("hw.wait.already")
    elif kind == "platform_notify":
        ok = _("dl.notify.done", email=email, platform=name)
        already = _("dl.notify.already")
    else:
        ok = _("dl.mobile.sent", email=email)
        already = _("dl.mobile.already")
    return {"ok": ok, "already": already, "rate": _("notice.rate"), "invalid": _("notice.invalid")}


def _send_confirmation(kind: str, email: str, platform: str, token: str) -> bool:
    from email_delivery import send_transactional_email
    from flask import url_for
    from i18n_platform import translate as _

    link = url_for("site_notice_unsubscribe", token=token, _external=True)
    name = {"mac": "macOS", "win": "Windows", "linux": "Linux"}.get(platform, platform)
    if kind == "hardware_wait":
        subject = _("notice.mail.hardware.subject")
        body = _("notice.mail.hardware.body", email=email)
    elif kind == "platform_notify":
        subject = _("notice.mail.notify.subject", platform=name)
        body = _("notice.mail.notify.body", email=email, platform=name)
    else:
        subject = _("notice.mail.download.subject")
        body = _("notice.mail.download.body", email=email)
    text = f"{body}\n\n{link}\n\n{_('notice.mail.unsub')}"
    return send_transactional_email(email, subject, text)


def submit_notice(
    conn,
    *,
    kind: str,
    email: str,
    platform: str = "",
    note: str = "",
    region: str = "",
    ip: str = "",
    skip_rate: bool = False,
) -> dict:
    """Store one address and send a confirmation. Returns status ok, already, rate, or invalid."""
    init_site_notice_tables(conn)
    email = (email or "").strip().lower()
    platform = (platform or "").strip().lower()
    note = (note or "").strip()[:500]
    region = (region or "").strip()[:120]
    if kind not in KINDS or not _valid_email(email):
        return {"status": "invalid", "message": _messages(kind if kind in KINDS else "download_link", email, platform)["invalid"]}
    if kind == "platform_notify" and platform not in PLATFORMS:
        return {"status": "invalid", "message": _messages(kind, email, platform)["invalid"]}
    if kind != "platform_notify":
        platform = ""

    messages = _messages(kind, email, platform)
    ip_hash = _hash(ip or "unknown")
    if not skip_rate:
        window = _window_minutes()
        hits = conn.execute(
            "SELECT COUNT(*) AS n FROM site_notice_hits WHERE ip_hash = ? AND created_at >= datetime('now', ?)",
            (ip_hash, f"-{window} minutes"),
        ).fetchone()["n"]
        if hits >= _limit():
            return {"status": "rate", "message": messages["rate"]}
        conn.execute("INSERT INTO site_notice_hits (ip_hash) VALUES (?)", (ip_hash,))
    existing = conn.execute(
        "SELECT id, unsubscribed FROM site_notices WHERE kind = ? AND email = ? AND platform = ?",
        (kind, email, platform),
    ).fetchone()
    if existing and not existing["unsubscribed"]:
        return {"status": "already", "message": messages["already"]}

    token = secrets.token_urlsafe(32)
    token_hash = _hash(token)
    if existing:
        conn.execute(
            """UPDATE site_notices
               SET note = ?, region = ?, token_hash = ?, unsubscribed = 0, created_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (note, region, token_hash, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO site_notices (kind, email, platform, note, region, token_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (kind, email, platform, note, region, token_hash),
        )
    if not _send_confirmation(kind, email, platform, token):
        conn.execute(
            "DELETE FROM site_notices WHERE kind = ? AND email = ? AND platform = ?",
            (kind, email, platform),
        )
        return {"status": "invalid", "message": messages["invalid"]}
    return {"status": "ok", "message": messages["ok"]}


def submit_platform_notices(conn, *, email: str, platforms, ip: str = "") -> dict:
    """Subscribe one address to one or more platform launch lists."""
    chosen = []
    seen = set()
    for raw in platforms or []:
        platform = (raw or "").strip().lower()
        if platform in PLATFORMS and platform not in seen:
            seen.add(platform)
            chosen.append(platform)
    if not chosen:
        return submit_notice(conn, kind="platform_notify", email=email, platform="", ip=ip)
    last = None
    for index, platform in enumerate(chosen):
        last = submit_notice(
            conn,
            kind="platform_notify",
            email=email,
            platform=platform,
            ip=ip,
            skip_rate=index > 0,
        )
        if last["status"] == "rate":
            return last
    return last


def unsubscribe_notice(conn, token: str) -> bool:
    init_site_notice_tables(conn)
    row = conn.execute(
        "SELECT id FROM site_notices WHERE token_hash = ?",
        (_hash(token or ""),),
    ).fetchone()
    if not row:
        return False
    conn.execute("UPDATE site_notices SET unsubscribed = 1 WHERE id = ?", (row["id"],))
    return True
