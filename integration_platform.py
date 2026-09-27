"""Integration Layer — optional plugins connecting Zintriq to external services."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from flask import abort, jsonify

from integration_catalog import all_plugin_seeds, catalog_api_payload, plugin_logo_url, plugin_public_meta

_log = logging.getLogger("app.integration")

REMOVED_PLUGIN_SLUGS = (
    "google_calendar",
    "notion",
    "google_business",
    "taiwan_pay",
    "ipeen",
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
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def purge_removed_plugins(conn) -> None:
    for slug in REMOVED_PLUGIN_SLUGS:
        conn.execute(
            """DELETE FROM user_integration_connections
               WHERE plugin_id IN (SELECT id FROM integration_plugins WHERE slug=?)""",
            (slug,),
        )
        conn.execute("DELETE FROM integration_plugins WHERE slug=?", (slug,))


def init_integration_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    purge_removed_plugins(conn)
    for p in all_plugin_seeds():
        conn.execute(
            """INSERT INTO integration_plugins (slug, name, provider, description, category, status)
               VALUES (?, ?, ?, ?, ?, 'available')
               ON CONFLICT(slug) DO UPDATE SET
                 name=excluded.name,
                 provider=excluded.provider,
                 description=excluded.description,
                 category=excluded.category,
                 updated_at=CURRENT_TIMESTAMP""",
            (p["slug"], p["name"], p["provider"], p["description"], p["category"]),
        )
    try:
        from payment_connect_plugin import init_payment_connection_tables
        init_payment_connection_tables(conn)
    except ImportError:
        _log.debug("payment_connect_import_skipped", exc_info=True, extra={"op": "init_integration_tables"})
        pass


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


def connection_to_api(row) -> dict:
    d = dict(row)
    status = d.get("status") or "disconnected"
    if status in ("pending", "disconnected"):
        status = "disconnected"
    elif d.get("access_token_enc") or status in ("connected", "active", "installed"):
        status = "connected" if status not in ("active", "error", "disconnected") else status
    if d.get("external_account_id") and status == "installed":
        status = "connected"
    return {
        "id": d["id"],
        "plugin_slug": d.get("plugin_slug"),
        "plugin_name": d.get("plugin_name"),
        "external_account_id": d.get("external_account_id"),
        "external_account_email": d.get("external_account_email"),
        "status": status,
        "expires_at": d.get("expires_at"),
        "created_at": d.get("created_at"),
    }


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
                if p["slug"] in REMOVED_PLUGIN_SLUGS:
                    continue
                meta = plugin_public_meta(p["slug"])
                if not meta:
                    continue
                conn_row = get_user_connection(conn, user_id, p["slug"])
                item = {
                    "slug": p["slug"],
                    "name": p["name"],
                    "provider": p["provider"],
                    "description": p["description"],
                    "category": p["category"],
                    "available": True,
                    "connection": None,
                    "regions": meta["regions"],
                    "region_labels": meta["region_labels"],
                    "checkout_ready": meta.get("checkout_ready", False),
                    "oauth_required": meta.get("oauth_required", False),
                    "credential_fields": meta.get("credential_fields", []),
                    "setup_guide": meta.get("setup_guide", {}),
                    "logo_url": meta.get("logo_url") or plugin_logo_url(p["slug"]),
                }
                if conn_row:
                    pay = conn.execute(
                        "SELECT * FROM payment_connections WHERE connection_id=?",
                        (conn_row["id"],),
                    ).fetchone()
                    conn_api = connection_to_api(conn_row)
                    if pay:
                        from payment_connect_plugin import payment_connection_to_api
                        conn_api["payment"] = payment_connection_to_api(pay)
                        if pay["account_status"] == "active" or pay["charges_enabled"]:
                            conn_api["status"] = "active"
                    item["connection"] = conn_api
                result.append(item)
        return jsonify(result)

    @app.get("/api/integrations/catalog")
    @login_required
    def api_integration_catalog():
        return jsonify(catalog_api_payload())

    @app.get("/api/integrations/connections/<plugin_slug>")
    @login_required
    def api_integration_connection_detail(plugin_slug):
        if plugin_slug in REMOVED_PLUGIN_SLUGS:
            abort(404)
        user_id = uid()
        with db() as conn:
            row = get_user_connection(conn, user_id, plugin_slug)
            if not row:
                return jsonify({"connected": False})
            logs = conn.execute(
                """SELECT event_type, status, error_message, created_at
                   FROM integration_event_logs WHERE connection_id=?
                   ORDER BY created_at DESC LIMIT 20""",
                (row["id"],),
            ).fetchall()
            payload = connection_to_api(row)
            payload["connected"] = row["status"] in ("connected", "active", "installed")
            payload["recent_logs"] = [dict(l) for l in logs]
        return jsonify(payload)

    app.init_integration_tables = init_integration_tables
