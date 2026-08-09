"""Google Calendar Plugin — optional scheduling sync for Business OS bookings."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import abort, jsonify, redirect, request, session, url_for

from bos.events import DomainEvent, subscribe
from bos.integration_crypto import decrypt_token, encrypt_token
from integration_platform import (
    connection_to_api,
    get_plugin_by_slug,
    get_user_connection,
    log_integration_event,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_CALENDAR_LIST = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
GOOGLE_CALENDAR_EVENTS = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
GOOGLE_CALENDAR_WATCH = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/watch"

SCOPES = (
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _google_config(app) -> dict | None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "",
    ).strip() or url_for("google_calendar_oauth_callback", _external=True)
    if not client_id or not client_secret:
        return None
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}


def _http_post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _http_get_json(url: str, access_token: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _http_request_json(method: str, url: str, access_token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {access_token}")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Google API {e.code}: {body[:200]}") from e


def _secret_key(app) -> str:
    return app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY", "")


def _store_tokens(conn, connection_id: int, access: str, refresh: str, expires_at: str, app) -> None:
    sk = _secret_key(app)
    conn.execute(
        """UPDATE user_integration_connections
           SET access_token_enc=?, refresh_token_enc=?, expires_at=?, status='connected', updated_at=?
           WHERE id=?""",
        (encrypt_token(access, sk), encrypt_token(refresh, sk) if refresh else "", expires_at, _now(), connection_id),
    )


def _load_access_token(conn, connection_row, app) -> str:
    sk = _secret_key(app)
    try:
        access = decrypt_token(connection_row["access_token_enc"], sk)
    except Exception as exc:
        conn.execute(
            """UPDATE user_integration_connections
               SET status='error', updated_at=? WHERE id=?""",
            (_now(), connection_row["id"]),
        )
        log_integration_event(
            conn, connection_row["id"], "oauth.token_decrypt", "error",
            "Token invalid — reconnect Google Calendar in Settings",
        )
        raise RuntimeError("Google Calendar token expired. Reconnect in Settings → Integrations.") from exc
    expires = connection_row["expires_at"]
    if expires and expires <= _now() and connection_row["refresh_token_enc"]:
        cfg = _google_config(app)
        if not cfg:
            raise RuntimeError("Google OAuth not configured")
        refresh = decrypt_token(connection_row["refresh_token_enc"], sk)
        token_data = _http_post_form(GOOGLE_TOKEN_URL, {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        })
        access = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        new_expires = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).replace(microsecond=0).isoformat()
        _store_tokens(conn, connection_row["id"], access, refresh, new_expires, app)
    return access


def _parse_booking_times(booking: dict) -> tuple[str, str]:
    start_raw = booking["starts_at"]
    end_raw = booking.get("ends_at")
    if "T" not in start_raw and len(start_raw) >= 16:
        start_raw = start_raw.replace(" ", "T")
    if not end_raw:
        try:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            end_dt = start_dt + timedelta(hours=1)
            end_raw = end_dt.isoformat()
        except ValueError:
            end_raw = start_raw
    elif "T" not in end_raw and len(end_raw) >= 16:
        end_raw = end_raw.replace(" ", "T")
    return start_raw, end_raw


def _build_calendar_event_body(conn, cal_event: dict, workspace_name: str, app) -> dict:
    title = cal_event.get("title") or "Event"
    summary = f"{workspace_name} — {title}"
    cal_url = url_for("bos.calendar", _external=True) + f"#event/{cal_event['id']}"
    description_parts = [cal_event.get("description") or ""]
    if cal_event.get("related_entity_type") and cal_event.get("related_entity_id"):
        description_parts.append(
            f"Related: {cal_event['related_entity_type']} #{cal_event['related_entity_id']}"
        )
    description_parts.append(f"Calendar event ID: {cal_event['id']}")
    description_parts.append(f"Business OS: {cal_url}")
    description = "\n".join(p for p in description_parts if p).strip()
    start, end = _parse_booking_times({
        "starts_at": cal_event["start_time"],
        "ends_at": cal_event.get("end_time"),
    })
    body = {
        "summary": summary,
        "description": description,
        "location": cal_event.get("location") or workspace_name,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
    }
    if cal_event.get("status") == "cancelled":
        body["status"] = "cancelled"
        body["summary"] = f"[Cancelled] {summary}"
    return body


def _parse_google_datetime(value: dict) -> str:
    if value.get("dateTime"):
        raw = value["dateTime"].replace("T", " ")
        return raw.split("+")[0].split("Z")[0][:19]
    if value.get("date"):
        return f"{value['date']} 00:00:00"
    return _now()[:19].replace("T", " ")


def _normalize_time_key(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("T", " ").strip()[:19]


def _webhook_base_url(app) -> str | None:
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base and app.config.get("PUBLIC_BASE_URL"):
        base = str(app.config["PUBLIC_BASE_URL"]).rstrip("/")
    if not base or not base.lower().startswith("https://"):
        return None
    return base


def _active_google_sync_targets(conn) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT uic.id AS connection_id, uic.user_id, cc.google_calendar_id,
                  (SELECT wm.workspace_id FROM workspace_members wm
                   WHERE wm.user_id=uic.user_id AND wm.status='active'
                   ORDER BY wm.workspace_id LIMIT 1) AS workspace_id
           FROM user_integration_connections uic
           JOIN integration_plugins ip ON ip.id=uic.plugin_id AND ip.slug='google_calendar'
           JOIN calendar_connections cc ON cc.connection_id=uic.id AND cc.sync_enabled=1
           WHERE uic.status IN ('connected', 'active')
             AND length(uic.access_token_enc) > 10"""
    ).fetchall()


def poll_google_calendar_inbound(app) -> dict:
    """Pull Google → OS for every active connection (background / fallback sync)."""
    from app import db

    summary = {"connections": 0, "imported": 0, "updated": 0, "errors": 0}
    with app.app_context():
        with db() as conn:
            targets = _active_google_sync_targets(conn)
            summary["connections"] = len(targets)
            for row in targets:
                ws_id = int(row["workspace_id"]) if row["workspace_id"] else None
                try:
                    result = sync_google_events_to_os(conn, app, int(row["user_id"]), ws_id)
                    summary["imported"] += int(result.get("imported") or 0)
                    summary["updated"] += int(result.get("updated") or 0)
                    summary["errors"] += int(result.get("errors") or 0)
                except Exception as exc:
                    summary["errors"] += 1
                    log_integration_event(
                        conn, int(row["connection_id"]), "calendar.poll", "error", str(exc)[:200],
                    )
    return summary


def refresh_all_google_watches(app) -> None:
    """Re-register Google push channels when PUBLIC_BASE_URL is HTTPS."""
    if not _webhook_base_url(app):
        return
    from app import db

    with app.app_context():
        with db() as conn:
            for row in _active_google_sync_targets(conn):
                try:
                    connection = conn.execute(
                        "SELECT * FROM user_integration_connections WHERE id=?",
                        (row["connection_id"],),
                    ).fetchone()
                    if not connection:
                        continue
                    access = _load_access_token(conn, connection, app)
                    _register_google_watch(
                        conn, app, int(row["connection_id"]), row["google_calendar_id"], access,
                    )
                except Exception as exc:
                    log_integration_event(
                        conn, int(row["connection_id"]), "calendar.watch_refresh", "error", str(exc)[:200],
                    )


def start_google_calendar_background_sync(app) -> None:
    """Background Google → OS sync so updates arrive without opening Calendar."""
    interval = int(os.environ.get("GOOGLE_CALENDAR_POLL_SECONDS", "60"))
    if interval <= 0:
        return
    if getattr(app, "_google_calendar_poll_started", False):
        return
    app._google_calendar_poll_started = True

    def _loop() -> None:
        poll_google_calendar_inbound(app)
        while True:
            time.sleep(interval)
            try:
                poll_google_calendar_inbound(app)
            except Exception:
                pass

    threading.Thread(target=_loop, daemon=True, name="google-calendar-poll").start()


def _register_google_watch(conn, app, connection_id: int, calendar_id: str, access: str) -> None:
    """Register push notifications when PUBLIC_BASE_URL is configured."""
    base = _webhook_base_url(app)
    if not base:
        return
    channel_id = secrets.token_urlsafe(16)
    webhook_url = f"{base}/api/integrations/google-calendar/webhook"
    cal_encoded = urllib.parse.quote(calendar_id, safe="@.")
    watch_url = GOOGLE_CALENDAR_WATCH.format(calendar_id=cal_encoded)
    expiration_ms = int((datetime.now(timezone.utc) + timedelta(days=6)).timestamp() * 1000)
    try:
        result = _http_request_json("POST", watch_url, access, {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "expiration": expiration_ms,
        })
        conn.execute("DELETE FROM google_calendar_watch_channels WHERE connection_id=?", (connection_id,))
        conn.execute(
            """INSERT INTO google_calendar_watch_channels
               (connection_id, channel_id, resource_id, expiration)
               VALUES (?, ?, ?, ?)""",
            (connection_id, channel_id, result.get("resourceId", ""), str(expiration_ms)),
        )
        log_integration_event(conn, connection_id, "calendar.watch_registered", "success")
    except Exception as exc:
        log_integration_event(conn, connection_id, "calendar.watch_registered", "error", str(exc))


def _record_sync_conflict(
    conn, workspace_id: int, user_id: int, event_id: int, ext_id: str,
    os_event: dict, g_ev: dict,
) -> None:
    g_start = _parse_google_datetime(g_ev.get("start", {}))
    g_end = _parse_google_datetime(g_ev.get("end", {}))
    g_title = (g_ev.get("summary") or "").strip()
    existing = conn.execute(
        """SELECT id FROM calendar_sync_conflicts
           WHERE calendar_event_id=? AND external_event_id=? AND status='open'""",
        (event_id, ext_id),
    ).fetchone()
    if existing:
        return
    conn.execute(
        """INSERT INTO calendar_sync_conflicts
           (workspace_id, user_id, calendar_event_id, external_event_id,
            os_start_time, google_start_time, os_title, google_title, os_end_time, google_end_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            workspace_id, user_id, event_id, ext_id,
            os_event["start_time"], g_start,
            os_event.get("title") or "", g_title,
            os_event.get("end_time"), g_end,
        ),
    )


def _google_fields_changed(os_event: dict, g_ev: dict) -> bool:
    g_start = _parse_google_datetime(g_ev.get("start", {}))
    g_title = (g_ev.get("summary") or "").strip()
    os_start = _normalize_time_key(os_event.get("start_time"))
    os_title = (os_event.get("title") or "").strip()
    g_status = g_ev.get("status")
    if g_status == "cancelled" and os_event.get("status") != "cancelled":
        return True
    return g_start != os_start or g_title != os_title


def _should_create_conflict(os_event: dict, g_ev: dict, ref: dict) -> bool:
    if not _google_fields_changed(os_event, g_ev):
        return False
    ref_updated = (ref.get("updated_at") or ref.get("created_at") or "")[:19]
    os_updated = (os_event.get("updated_at") or "")[:19]
    return os_updated > ref_updated


def _google_sync_context(conn, user_id: int):
    connection = get_user_connection(conn, user_id, "google_calendar")
    if not connection or connection["status"] not in ("connected", "active", "installed"):
        return None, None
    cal = conn.execute(
        "SELECT * FROM calendar_connections WHERE connection_id=? AND sync_enabled=1",
        (connection["id"],),
    ).fetchone()
    if not cal:
        return connection, None
    return connection, cal


def sync_google_events_to_os(conn, app, user_id: int, workspace_id: int | None) -> dict:
    """Pull Google Calendar events into Business OS calendar_events."""
    connection, cal = _google_sync_context(conn, user_id)
    if not connection:
        return {"imported": 0, "updated": 0, "errors": 0, "skipped": "not_connected"}
    if not cal:
        return {"imported": 0, "updated": 0, "errors": 0, "skipped": "no_calendar_selected"}
    if not workspace_id:
        row = conn.execute(
            """SELECT workspace_id FROM workspace_members
               WHERE user_id=? AND status='active' ORDER BY workspace_id LIMIT 1""",
            (user_id,),
        ).fetchone()
        if not row:
            return {"imported": 0, "updated": 0, "errors": 0, "skipped": "no_workspace"}
        workspace_id = int(row["workspace_id"])

    try:
        access = _load_access_token(conn, connection, app)
    except Exception as exc:
        log_integration_event(conn, connection["id"], "calendar.import", "error", str(exc))
        return {"imported": 0, "updated": 0, "errors": 1, "skipped": str(exc)}

    time_min = (datetime.now(timezone.utc) - timedelta(days=30)).replace(microsecond=0).isoformat()
    time_max = (datetime.now(timezone.utc) + timedelta(days=120)).replace(microsecond=0).isoformat()
    calendar_id = urllib.parse.quote(cal["google_calendar_id"], safe="@.")
    params = urllib.parse.urlencode({
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "250",
    })
    url = f"{GOOGLE_CALENDAR_EVENTS.format(calendar_id=calendar_id)}?{params}"

    try:
        data = _http_get_json(url, access)
    except Exception as exc:
        log_integration_event(conn, connection["id"], "calendar.import", "error", str(exc))
        return {"imported": 0, "updated": 0, "errors": 1, "skipped": str(exc)}

    imported, updated, errors, conflicts = 0, 0, 0, 0
    seen_google_ids: set[str] = set()
    for g_ev in data.get("items", []):
        ext_id = g_ev.get("id")
        if not ext_id:
            continue
        seen_google_ids.add(ext_id)
        try:
            start_time = _parse_google_datetime(g_ev.get("start", {}))
            end_time = _parse_google_datetime(g_ev.get("end", {}))
            title = (g_ev.get("summary") or "Google Calendar event").strip()
            description = (g_ev.get("description") or "").strip()
            location = (g_ev.get("location") or "").strip()
            status = "cancelled" if g_ev.get("status") == "cancelled" else "confirmed"

            ref = conn.execute(
                """SELECT * FROM external_references
                   WHERE external_object_id=? AND external_provider='google_calendar' AND user_id=?""",
                (ext_id, user_id),
            ).fetchone()

            if ref:
                os_event = conn.execute(
                    "SELECT * FROM calendar_events WHERE id=?", (ref["business_object_id"],)
                ).fetchone()
                if os_event:
                    if _should_create_conflict(dict(os_event), g_ev, dict(ref)):
                        _record_sync_conflict(
                            conn, workspace_id, user_id, int(os_event["id"]), ext_id,
                            dict(os_event), g_ev,
                        )
                        conflicts += 1
                        continue
                    conn.execute(
                        """UPDATE calendar_events SET
                           title=?, description=?, start_time=?, end_time=?, location=?,
                           status=?, updated_by=?, updated_at=?
                           WHERE id=?""",
                        (title, description, start_time, end_time, location, status, user_id, _now(), os_event["id"]),
                    )
                    conn.execute(
                        "UPDATE external_references SET sync_status='synced', updated_at=? WHERE id=?",
                        (_now(), ref["id"]),
                    )
                    updated += 1
                continue

            existing = conn.execute(
                """SELECT id FROM calendar_events
                   WHERE workspace_id=? AND source='google_calendar' AND external_event_id=?""",
                (workspace_id, ext_id),
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE calendar_events SET
                       title=?, description=?, start_time=?, end_time=?, location=?,
                       status=?, updated_by=?, updated_at=?
                       WHERE id=?""",
                    (title, description, start_time, end_time, location, status, user_id, _now(), existing["id"]),
                )
                updated += 1
            else:
                conn.execute(
                    """INSERT INTO calendar_events
                       (workspace_id, created_by, title, description, event_type, start_time, end_time,
                        location, visibility, source, external_provider, external_event_id, status,
                        operational_status, updated_by, updated_at)
                       VALUES (?, ?, ?, ?, 'business_event', ?, ?, ?, 'workspace', 'google_calendar', 'google_calendar', ?, ?, 'scheduled', ?, ?)""",
                    (
                        workspace_id, user_id, title, description,
                        start_time, end_time, location, ext_id, status, user_id, _now(),
                    ),
                )
                imported += 1
        except Exception:
            errors += 1

    # Google-only imports removed from Google → archive in OS
    stale = conn.execute(
        """SELECT id, external_event_id FROM calendar_events
           WHERE workspace_id=? AND source='google_calendar' AND status NOT IN ('archived', 'deleted')
           AND external_event_id IS NOT NULL""",
        (workspace_id,),
    ).fetchall()
    for row in stale:
        if row["external_event_id"] not in seen_google_ids:
            conn.execute(
                "UPDATE calendar_events SET status='archived', updated_by=?, updated_at=? WHERE id=?",
                (user_id, _now(), row["id"]),
            )
            updated += 1

    log_integration_event(
        conn, connection["id"], "calendar.import",
        "success" if errors == 0 else "error",
        json.dumps({"imported": imported, "updated": updated, "errors": errors, "conflicts": conflicts}),
    )
    conn.execute(
        "UPDATE user_integration_connections SET status='active', updated_at=? WHERE id=?",
        (_now(), connection["id"]),
    )
    return {"imported": imported, "updated": updated, "errors": errors, "conflicts": conflicts}


def sync_all_calendars(conn, app, user_id: int, workspace_id: int | None = None) -> dict:
    """Two-way sync: OS → Google, then Google → OS."""
    outbound = sync_pending_calendar_events(conn, app, user_id)
    inbound = sync_google_events_to_os(conn, app, user_id, workspace_id)
    return {"outbound": outbound, "inbound": inbound}


def sync_calendar_event_to_google(conn, app, user_id: int, calendar_event_id: int, event_type: str) -> None:
    """Sync a Business OS calendar event to the user's connected Google Calendar."""
    cal_event = conn.execute("SELECT * FROM calendar_events WHERE id=?", (calendar_event_id,)).fetchone()
    if not cal_event:
        return
    if cal_event["source"] == "google_calendar":
        return
    if cal_event["status"] in ("deleted", "archived") and event_type == "calendar.created":
        return
    connection, cal = _google_sync_context(conn, user_id)
    if not connection or not cal:
        return

    ws = conn.execute("SELECT name FROM workspaces WHERE id=?", (cal_event["workspace_id"],)).fetchone()
    workspace_name = ws["name"] if ws else "Business OS"

    try:
        access = _load_access_token(conn, connection, app)
    except Exception as exc:
        log_integration_event(conn, connection["id"], event_type, "error", str(exc))
        conn.execute(
            "UPDATE user_integration_connections SET status='error', updated_at=? WHERE id=?",
            (_now(), connection["id"]),
        )
        return

    ref = conn.execute(
        """SELECT * FROM external_references
           WHERE object_type='calendar_event' AND business_object_id=? AND user_id=?
           AND external_provider='google_calendar'""",
        (calendar_event_id, user_id),
    ).fetchone()

    event_body = _build_calendar_event_body(conn, dict(cal_event), workspace_name, app)
    calendar_id = urllib.parse.quote(cal["google_calendar_id"], safe="@.")
    events_url = GOOGLE_CALENDAR_EVENTS.format(calendar_id=calendar_id)

    try:
        if event_type in ("calendar.deleted", "calendar.cancelled") or cal_event["status"] in ("archived", "deleted", "cancelled"):
            if ref:
                ext_id = urllib.parse.quote(ref["external_object_id"], safe="@.")
                delete_url = f"{events_url}/{ext_id}"
                try:
                    _http_request_json("DELETE", delete_url, access)
                except RuntimeError as exc:
                    if "404" not in str(exc) and "410" not in str(exc):
                        raise
                conn.execute("DELETE FROM external_references WHERE id=?", (ref["id"],))
                log_integration_event(
                    conn, connection["id"],
                    "calendar.event.deleted" if event_type == "calendar.deleted" else "calendar.event.cancelled",
                    "success",
                )
            return
        if not ref:
            result = _http_request_json("POST", events_url, access, event_body)
            ext_id = result.get("id")
            if not ext_id:
                raise RuntimeError("Google API returned no event id")
            conn.execute(
                """INSERT INTO external_references
                   (workspace_id, user_id, object_type, business_object_id, external_provider, external_object_id, sync_status)
                   VALUES (?, ?, 'calendar_event', ?, 'google_calendar', ?, 'synced')""",
                (cal_event["workspace_id"], user_id, calendar_event_id, ext_id),
            )
            conn.execute(
                "UPDATE calendar_events SET external_provider='google_calendar', external_event_id=? WHERE id=?",
                (ext_id, calendar_event_id),
            )
            log_integration_event(conn, connection["id"], "calendar.event.created", "success")
        else:
            ext_id = urllib.parse.quote(ref["external_object_id"], safe="@.")
            patch_url = f"{events_url}/{ext_id}"
            _http_request_json("PATCH", patch_url, access, event_body)
            conn.execute(
                "UPDATE external_references SET sync_status='synced', updated_at=? WHERE id=?",
                (_now(), ref["id"]),
            )
            conn.execute(
                "UPDATE calendar_events SET external_provider='google_calendar', external_event_id=? WHERE id=?",
                (ref["external_object_id"], calendar_event_id),
            )
            log_integration_event(conn, connection["id"], "calendar.event.updated", "success")
        conn.execute(
            "UPDATE user_integration_connections SET status='active', updated_at=? WHERE id=?",
            (_now(), connection["id"]),
        )
    except Exception as exc:
        log_integration_event(conn, connection["id"], event_type, "error", str(exc))
        if ref:
            conn.execute(
                "UPDATE external_references SET sync_status='error', updated_at=? WHERE id=?",
                (_now(), ref["id"]),
            )


def count_pending_calendar_events(conn, user_id: int) -> int:
    """Count events not yet linked to this user's Google Calendar."""
    connection, cal = _google_sync_context(conn, user_id)
    if not connection or not cal:
        return 0
    workspace_rows = conn.execute(
        "SELECT workspace_id FROM workspace_members WHERE user_id=? AND status='active'",
        (user_id,),
    ).fetchall()
    workspace_ids = [int(r["workspace_id"]) for r in workspace_rows]
    if not workspace_ids:
        return 0
    placeholders = ",".join("?" * len(workspace_ids))
    row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM calendar_events ce
            WHERE ce.workspace_id IN ({placeholders})
              AND ce.source = 'business_os'
              AND ce.status NOT IN ('deleted', 'archived')
              AND (
                ce.visibility = 'workspace'
                OR ce.created_by = ?
                OR ce.id IN (SELECT event_id FROM calendar_participants WHERE user_id = ?)
              )
              AND ce.id NOT IN (
                SELECT business_object_id FROM external_references
                WHERE object_type='calendar_event' AND user_id=? AND external_provider='google_calendar'
              )""",
        (*workspace_ids, user_id, user_id, user_id),
    ).fetchone()
    return int(row["c"]) if row else 0


def sync_pending_calendar_events(conn, app, user_id: int) -> dict:
    """Backfill: push unsynced workspace calendar events to the user's Google Calendar."""
    connection = get_user_connection(conn, user_id, "google_calendar")
    if not connection:
        return {"synced": 0, "errors": 0, "skipped": "not_connected"}
    cal = conn.execute(
        "SELECT 1 FROM calendar_connections WHERE connection_id=? AND sync_enabled=1",
        (connection["id"],),
    ).fetchone()
    if not cal:
        return {"synced": 0, "errors": 0, "skipped": "no_calendar_selected"}

    workspace_rows = conn.execute(
        "SELECT workspace_id FROM workspace_members WHERE user_id=? AND status='active'",
        (user_id,),
    ).fetchall()
    workspace_ids = [int(r["workspace_id"]) for r in workspace_rows]
    if not workspace_ids:
        return {"synced": 0, "errors": 0, "skipped": "no_workspace"}

    placeholders = ",".join("?" * len(workspace_ids))
    pending = conn.execute(
        f"""SELECT ce.id FROM calendar_events ce
            WHERE ce.workspace_id IN ({placeholders})
              AND ce.source = 'business_os'
              AND ce.status NOT IN ('deleted', 'archived')
              AND (
                ce.visibility = 'workspace'
                OR ce.created_by = ?
                OR ce.id IN (SELECT event_id FROM calendar_participants WHERE user_id = ?)
              )
              AND ce.id NOT IN (
                SELECT business_object_id FROM external_references
                WHERE object_type='calendar_event' AND user_id=? AND external_provider='google_calendar'
              )
            ORDER BY ce.start_time ASC
            LIMIT 200""",
        (*workspace_ids, user_id, user_id, user_id),
    ).fetchall()

    synced, errors = 0, 0
    for row in pending:
        try:
            sync_calendar_event_to_google(conn, app, user_id, int(row["id"]), "calendar.created")
            ref = conn.execute(
                """SELECT 1 FROM external_references
                   WHERE object_type='calendar_event' AND business_object_id=? AND user_id=?
                   AND external_provider='google_calendar' AND sync_status='synced'""",
                (row["id"], user_id),
            ).fetchone()
            if ref:
                synced += 1
            else:
                errors += 1
        except Exception:
            errors += 1
    return {"synced": synced, "errors": errors, "pending": len(pending)}


def _calendar_event_handler(conn: sqlite3.Connection, event: DomainEvent, app) -> None:
    if event.event_type not in (
        "calendar.created", "calendar.updated", "calendar.cancelled", "calendar.deleted",
    ):
        return
    if event.object_type != "calendar_event":
        return
    cal_row = conn.execute("SELECT * FROM calendar_events WHERE id=?", (event.object_id,)).fetchone()
    if not cal_row:
        return
    user_ids: set[int] = set()
    if cal_row["created_by"]:
        user_ids.add(int(cal_row["created_by"]))
    if event.user_id:
        user_ids.add(int(event.user_id))
    participant_rows = conn.execute(
        "SELECT user_id FROM calendar_participants WHERE event_id=? AND user_id IS NOT NULL",
        (event.object_id,),
    ).fetchall()
    for pr in participant_rows:
        user_ids.add(int(pr["user_id"]))
    if not user_ids:
        return
    for sync_user_id in user_ids:
        sync_calendar_event_to_google(conn, app, sync_user_id, int(event.object_id), event.event_type)


def register_google_calendar_plugin(app) -> None:
    from app import current_user, db, login_required

    subscribe(lambda conn, ev: _calendar_event_handler(conn, ev, app))

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    @app.get("/api/integrations/google-calendar/oauth/start")
    @login_required
    def google_calendar_oauth_start():
        cfg = _google_config(app)
        if not cfg:
            return jsonify({"error": "Google Calendar is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."}), 503
        user_id = uid()
        state = secrets.token_urlsafe(32)
        session["google_oauth_state"] = state
        session["google_oauth_user_id"] = user_id
        params = urllib.parse.urlencode({
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        })
        return jsonify({"auth_url": f"{GOOGLE_AUTH_URL}?{params}"})

    @app.get("/api/integrations/google-calendar/oauth/callback")
    def google_calendar_oauth_callback():
        cfg = _google_config(app)
        if not cfg:
            return redirect("/app/settings?integration_error=not_configured")
        if request.args.get("error"):
            return redirect(f"/app/settings?integration_error={request.args.get('error')}")
        state = request.args.get("state", "")
        if state != session.get("google_oauth_state"):
            return redirect("/app/settings?integration_error=invalid_state")
        user_id = session.get("google_oauth_user_id")
        if not user_id or not current_user() or int(current_user()["id"]) != int(user_id):
            return redirect(url_for("login", next=request.url))
        code = request.args.get("code")
        if not code:
            return redirect("/app/settings?integration_error=no_code")
        try:
            token_data = _http_post_form(GOOGLE_TOKEN_URL, {
                "code": code,
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "redirect_uri": cfg["redirect_uri"],
                "grant_type": "authorization_code",
            })
        except Exception:
            return redirect("/app/settings?integration_error=token_exchange_failed")
        access = token_data.get("access_token", "")
        refresh = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).replace(microsecond=0).isoformat()
        email = ""
        try:
            profile = _http_get_json(GOOGLE_USERINFO_URL, access)
            email = profile.get("email", "")
        except Exception:
            pass
        with db() as conn:
            plugin = get_plugin_by_slug(conn, "google_calendar")
            if not plugin:
                return redirect("/app/settings?integration_error=plugin_missing")
            existing = conn.execute(
                "SELECT id FROM user_integration_connections WHERE user_id=? AND plugin_id=?",
                (user_id, plugin["id"]),
            ).fetchone()
            if existing:
                conn_id = existing["id"]
                _store_tokens(conn, conn_id, access, refresh, expires_at, app)
                conn.execute(
                    "UPDATE user_integration_connections SET external_account_email=?, status='connected', updated_at=? WHERE id=?",
                    (email, _now(), conn_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO user_integration_connections
                       (user_id, plugin_id, external_account_id, external_account_email,
                        access_token_enc, refresh_token_enc, expires_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'connected')""",
                    (
                        user_id, plugin["id"], email, email,
                        encrypt_token(access, _secret_key(app)),
                        encrypt_token(refresh, _secret_key(app)) if refresh else "",
                        expires_at,
                    ),
                )
                conn_id = cur.lastrowid
            log_integration_event(conn, conn_id, "oauth.connected", "success")
            # Auto-select primary Google calendar when available
            try:
                access = _load_access_token(conn, conn.execute(
                    "SELECT * FROM user_integration_connections WHERE id=?", (conn_id,)
                ).fetchone(), app)
                cal_data = _http_get_json(GOOGLE_CALENDAR_LIST, access)
                items = cal_data.get("items", [])
                primary = next((c for c in items if c.get("primary")), items[0] if items else None)
                if primary:
                    conn.execute(
                        """INSERT INTO calendar_connections (connection_id, google_calendar_id, calendar_name, sync_enabled)
                           VALUES (?, ?, ?, 1)
                           ON CONFLICT(connection_id) DO UPDATE SET
                             google_calendar_id=excluded.google_calendar_id,
                             calendar_name=excluded.calendar_name,
                             sync_enabled=1,
                             updated_at=?""",
                        (conn_id, primary["id"], primary.get("summary", primary["id"]), _now()),
                    )
                    conn.execute(
                        "UPDATE user_integration_connections SET status='active', updated_at=? WHERE id=?",
                        (_now(), conn_id),
                    )
                    try:
                        access = _load_access_token(conn, conn.execute(
                            "SELECT * FROM user_integration_connections WHERE id=?", (conn_id,)
                        ).fetchone(), app)
                        _register_google_watch(conn, app, conn_id, primary["id"], access)
                    except Exception:
                        pass
            except Exception:
                pass
        session.pop("google_oauth_state", None)
        return redirect("/app/settings?integration=google_calendar&step=select-calendar")

    @app.get("/api/integrations/google-calendar/calendars")
    @login_required
    def google_calendar_list():
        user_id = uid()
        cfg = _google_config(app)
        if not cfg:
            return jsonify({"error": "Google Calendar not configured"}), 503
        with db() as conn:
            connection = get_user_connection(conn, user_id, "google_calendar")
            if not connection:
                return jsonify({"error": "Not connected"}), 404
            try:
                access = _load_access_token(conn, connection, app)
                data = _http_get_json(GOOGLE_CALENDAR_LIST, access)
            except Exception as exc:
                log_integration_event(conn, connection["id"], "calendar.list", "error", str(exc))
                return jsonify({"error": "Could not load calendars"}), 502
            calendars = [
                {"id": c["id"], "name": c.get("summary", c["id"]), "primary": c.get("primary", False)}
                for c in data.get("items", [])
            ]
        return jsonify(calendars)

    @app.post("/api/integrations/google-calendar/calendar")
    @login_required
    def google_calendar_select():
        user_id = uid()
        data = request.get_json(silent=True) or {}
        calendar_id = (data.get("google_calendar_id") or "").strip()
        calendar_name = (data.get("calendar_name") or "").strip()
        if not calendar_id:
            return jsonify({"error": "google_calendar_id required"}), 400
        with db() as conn:
            connection = get_user_connection(conn, user_id, "google_calendar")
            if not connection:
                return jsonify({"error": "Not connected"}), 404
            conn.execute(
                """INSERT INTO calendar_connections (connection_id, google_calendar_id, calendar_name, sync_enabled)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT(connection_id) DO UPDATE SET
                     google_calendar_id=excluded.google_calendar_id,
                     calendar_name=excluded.calendar_name,
                     sync_enabled=1,
                     updated_at=?""",
                (connection["id"], calendar_id, calendar_name or calendar_id, _now()),
            )
            conn.execute(
                "UPDATE user_integration_connections SET status='active', updated_at=? WHERE id=?",
                (_now(), connection["id"]),
            )
            log_integration_event(conn, connection["id"], "calendar.selected", "success")
            ws_id = session.get("active_workspace_id")
            try:
                access = _load_access_token(conn, connection, app)
                _register_google_watch(conn, app, connection["id"], calendar_id, access)
            except Exception:
                pass
            sync_result = sync_all_calendars(conn, app, user_id, int(ws_id) if ws_id else None)
            log_integration_event(
                conn, connection["id"], "calendar.backfill",
                "success" if sync_result.get("outbound", {}).get("errors", 0) == 0 else "error",
                json.dumps(sync_result),
            )
        return jsonify({"ok": True, "status": "active", "sync": sync_result})

    @app.post("/api/integrations/google-calendar/sync")
    @login_required
    def google_calendar_sync_now():
        user_id = uid()
        ws_id = session.get("active_workspace_id")
        with db() as conn:
            result = sync_all_calendars(conn, app, user_id, int(ws_id) if ws_id else None)
            connection = get_user_connection(conn, user_id, "google_calendar")
            if connection:
                log_integration_event(
                    conn, connection["id"], "calendar.manual_sync",
                    "success" if result.get("outbound", {}).get("errors", 0) == 0 else "error",
                    json.dumps(result),
                )
        return jsonify(result)

    @app.post("/api/integrations/google-calendar/webhook")
    def google_calendar_webhook():
        """Google Calendar push notification endpoint (requires PUBLIC_BASE_URL)."""
        channel_id = request.headers.get("X-Goog-Channel-ID", "")
        resource_state = request.headers.get("X-Goog-Resource-State", "")
        if resource_state == "sync":
            return "", 200
        with db() as conn:
            watch = conn.execute(
                """SELECT wc.*, cc.google_calendar_id, uic.user_id
                   FROM google_calendar_watch_channels wc
                   JOIN user_integration_connections uic ON uic.id=wc.connection_id
                   JOIN calendar_connections cc ON cc.connection_id=uic.id
                   WHERE wc.channel_id=?""",
                (channel_id,),
            ).fetchone()
            if not watch:
                return "", 404
            ws_row = conn.execute(
                """SELECT workspace_id FROM workspace_members
                   WHERE user_id=? AND status='active' ORDER BY workspace_id LIMIT 1""",
                (watch["user_id"],),
            ).fetchone()
            ws_id = int(ws_row["workspace_id"]) if ws_row else None
            sync_google_events_to_os(conn, app, int(watch["user_id"]), ws_id)
            log_integration_event(conn, watch["connection_id"], "calendar.webhook", "success", resource_state)
        return "", 200

    @app.post("/api/integrations/google-calendar/disconnect")
    @login_required
    def google_calendar_disconnect():
        user_id = uid()
        with db() as conn:
            connection = get_user_connection(conn, user_id, "google_calendar")
            if not connection:
                return jsonify({"ok": True})
            conn.execute("DELETE FROM calendar_connections WHERE connection_id=?", (connection["id"],))
            conn.execute(
                """UPDATE user_integration_connections
                   SET access_token_enc='', refresh_token_enc='', expires_at=NULL,
                       status='disconnected', updated_at=?
                   WHERE id=? AND user_id=?""",
                (_now(), connection["id"], user_id),
            )
            log_integration_event(conn, connection["id"], "oauth.disconnected", "success")
        return jsonify({"ok": True})

    @app.get("/api/integrations/google-calendar/status")
    @login_required
    def google_calendar_status():
        user_id = uid()
        configured = _google_config(app) is not None
        with db() as conn:
            connection = get_user_connection(conn, user_id, "google_calendar")
            if not connection:
                return jsonify({"configured": configured, "connected": False, "status": "not_connected"})
            cal = conn.execute(
                "SELECT * FROM calendar_connections WHERE connection_id=?",
                (connection["id"],),
            ).fetchone()
            merged = dict(connection)
            if cal:
                merged.update(dict(cal))
            payload = {
                "configured": configured,
                "connected": connection["status"] in ("connected", "active"),
                **connection_to_api(merged, include_calendar=True),
            }
            logs = conn.execute(
                """SELECT event_type, status, error_message, created_at
                   FROM integration_event_logs WHERE connection_id=?
                   ORDER BY created_at DESC LIMIT 20""",
                (connection["id"],),
            ).fetchall()
            payload["recent_logs"] = [dict(l) for l in logs]
            payload["pending_sync"] = count_pending_calendar_events(conn, user_id)
            user = current_user()
            payload["signed_in_as"] = user["email"] if user else ""
            watch = conn.execute(
                "SELECT channel_id, expiration FROM google_calendar_watch_channels WHERE connection_id=?",
                (connection["id"],),
            ).fetchone()
            payload["webhook_active"] = bool(watch)
            payload["background_poll_seconds"] = int(os.environ.get("GOOGLE_CALENDAR_POLL_SECONDS", "60"))
        return jsonify(payload)

    start_google_calendar_background_sync(app)

    def _deferred_watch_refresh() -> None:
        try:
            with app.app_context():
                refresh_all_google_watches(app)
        except Exception:
            pass

    threading.Thread(
        target=_deferred_watch_refresh,
        daemon=True,
        name="google-calendar-watch-refresh",
    ).start()
