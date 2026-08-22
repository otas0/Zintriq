"""Zintriq Integration Layer."""

from integrations.subscription import init_subscription_tables
from integrations.user_profile import init_user_profile_tables

WEBHOOK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS integration_webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    external_id TEXT,
    workspace_id INTEGER,
    payload_summary TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'received',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_webhook_events_provider ON integration_webhook_events(provider, created_at DESC);
"""


def init_integrations_core_tables(conn) -> None:
    init_user_profile_tables(conn)
    init_subscription_tables(conn)
    conn.executescript(WEBHOOK_SCHEMA_SQL)
