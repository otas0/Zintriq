"""Integration Layer — optional plugins connecting Business OS to external services."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import abort, jsonify

PLUGIN_SEED = (
    {
        "slug": "google_calendar",
        "name": "Google Calendar",
        "provider": "google",
        "description": "Scheduling integration — sync bookings to your calendar",
        "category": "scheduling",
    },
    {
        "slug": "stripe",
        "name": "Stripe",
        "provider": "stripe",
        "description": "Payment integration — accept payments via Stripe",
        "category": "payments",
    },
    {
        "slug": "notion",
        "name": "Notion",
        "provider": "notion",
        "description": "Documentation integration — sync records to Notion",
        "category": "documentation",
    },
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS integration_plugins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_integration_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plugin_id INTEGER NOT NULL,
    external_account_id TEXT,
    external_account_email TEXT,
    access_token_enc TEXT NOT NULL DEFAULT '',
    refresh_token_enc TEXT NOT NULL DEFAULT '',
    expires_at TEXT,
    status TEXT NOT NULL DEFAULT 'installed',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, plugin_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(plugin_id) REFERENCES integration_plugins(id)
);
CREATE INDEX IF NOT EXISTS idx_user_integration_user ON user_integration_connections(user_id);

CREATE TABLE IF NOT EXISTS calendar_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL UNIQUE,
    google_calendar_id TEXT NOT NULL,
    calendar_name TEXT NOT NULL,
    sync_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(connection_id) REFERENCES user_integration_connections(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS external_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER,
    user_id INTEGER NOT NULL,
    object_type TEXT NOT NULL,
    business_object_id INTEGER NOT NULL,
    external_provider TEXT NOT NULL,
    external_object_id TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'synced',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(object_type, business_object_id, external_provider, user_id)
);
CREATE INDEX IF NOT EXISTS idx_external_refs_object ON external_references(object_type, business_object_id);

CREATE TABLE IF NOT EXISTS integration_event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(connection_id) REFERENCES user_integration_connections(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_integration_logs_conn ON integration_event_logs(connection_id, created_at DESC);

CREATE TABLE IF NOT EXISTS google_calendar_watch_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL,
    channel_id TEXT NOT NULL UNIQUE,
    resource_id TEXT NOT NULL,
    expiration TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(connection_id) REFERENCES user_integration_connections(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gcal_watch_conn ON google_calendar_watch_channels(connection_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_integration_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    for p in PLUGIN_SEED:
        conn.execute(
            """INSERT OR IGNORE INTO integration_plugins (slug, name, provider, description, category, status)
               VALUES (?, ?, ?, ?, ?, 'available')""",
            (p["slug"], p["name"], p["provider"], p["description"], p["category"]),
        )


def get_plugin_by_slug(conn, slug: str):
    return conn.execute("SELECT * FROM integration_plugins WHERE slug=?", (slug,)).fetchone()


def get_user_connection(conn, user_id: int, plugin_slug: str):
    return conn.execute(
        """SELECT uic.*, ip.slug AS plugin_slug, ip.name AS plugin_name
           FROM user_integration_connections uic
           JOIN integration_plugins ip ON ip.id = uic.plugin_id
           WHERE uic.user_id=? AND ip.slug=?""",
        (user_id, plugin_slug),
    ).fetchone()


def log_integration_event(conn, connection_id: int, event_type: str, status: str, error: str = "") -> None:
    conn.execute(
        """INSERT INTO integration_event_logs (connection_id, event_type, status, error_message)
           VALUES (?, ?, ?, ?)""",
        (connection_id, event_type, status, error[:500]),
    )


def connection_to_api(row, *, include_calendar: bool = False) -> dict:
    d = dict(row)
    status = d.get("status") or "installed"
    cal = d.get("calendar_name")
    if d.get("sync_enabled") and d.get("google_calendar_id"):
        status = "active"
    elif d.get("access_token_enc") or d.get("status") == "connected":
        status = "connected" if not cal else "active"
    payload = {
        "id": d["id"],
        "plugin_slug": d.get("plugin_slug"),
        "plugin_name": d.get("plugin_name"),
        "external_account_email": d.get("external_account_email"),
        "status": status,
        "expires_at": d.get("expires_at"),
        "created_at": d.get("created_at"),
    }
    if include_calendar:
        payload["calendar"] = {
            "id": d.get("google_calendar_id"),
            "name": d.get("calendar_name"),
            "sync_enabled": bool(d.get("sync_enabled")),
        } if d.get("google_calendar_id") else None
    return payload


def register_integration_platform(app) -> None:
    from app import current_user, db, login_required

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    @app.get("/api/integrations/plugins")
    @login_required
    def api_integration_plugins():
        user_id = uid()
        with db() as conn:
            plugins = conn.execute(
                "SELECT * FROM integration_plugins ORDER BY name",
            ).fetchall()
            result = []
            for p in plugins:
                conn_row = get_user_connection(conn, user_id, p["slug"])
                item = {
                    "slug": p["slug"],
                    "name": p["name"],
                    "provider": p["provider"],
                    "description": p["description"],
                    "category": p["category"],
                    "available": True,
                    "connection": None,
                }
                if conn_row:
                    cal = conn.execute(
                        "SELECT * FROM calendar_connections WHERE connection_id=?",
                        (conn_row["id"],),
                    ).fetchone()
                    merged = dict(conn_row)
                    if cal:
                        merged.update(dict(cal))
                    item["connection"] = connection_to_api(merged, include_calendar=p["slug"] == "google_calendar")
                result.append(item)
        return jsonify(result)

    @app.get("/api/integrations/connections/<plugin_slug>")
    @login_required
    def api_integration_connection_detail(plugin_slug):
        user_id = uid()
        with db() as conn:
            row = get_user_connection(conn, user_id, plugin_slug)
            if not row:
                return jsonify({"connected": False})
            cal = conn.execute(
                "SELECT * FROM calendar_connections WHERE connection_id=?",
                (row["id"],),
            ).fetchone()
            merged = dict(row)
            if cal:
                merged.update(dict(cal))
            logs = conn.execute(
                """SELECT event_type, status, error_message, created_at
                   FROM integration_event_logs WHERE connection_id=?
                   ORDER BY created_at DESC LIMIT 20""",
                (row["id"],),
            ).fetchall()
            payload = connection_to_api(merged, include_calendar=plugin_slug == "google_calendar")
            payload["connected"] = row["status"] in ("connected", "active", "installed")
            payload["recent_logs"] = [dict(l) for l in logs]
        return jsonify(payload)

    app.init_integration_tables = init_integration_tables
