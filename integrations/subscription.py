"""Workspace subscription records — external payment relationship only."""

from __future__ import annotations

from datetime import datetime

SUBSCRIPTION_STATUSES = ("inactive", "active", "past_due", "cancelled", "trialing")
SUBSCRIPTION_PLANS = ("free", "starter", "pro", "enterprise")

SUBSCRIPTION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workspace_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'none',
    provider_customer_id TEXT,
    provider_subscription_id TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'inactive',
    current_period_end TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workspace_subscriptions_status ON workspace_subscriptions(status);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_subscription_tables(conn) -> None:
    conn.executescript(SUBSCRIPTION_SCHEMA_SQL)


def get_workspace_subscription(conn, workspace_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM workspace_subscriptions WHERE workspace_id=?", (workspace_id,),
    ).fetchone()
    return subscription_to_api(row) if row else None


def ensure_workspace_subscription(conn, workspace_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM workspace_subscriptions WHERE workspace_id=?", (workspace_id,),
    ).fetchone()
    if row:
        return subscription_to_api(row)
    now = _now()
    conn.execute(
        """INSERT INTO workspace_subscriptions
           (workspace_id, provider, plan, status, created_at, updated_at)
           VALUES (?, 'none', 'free', 'inactive', ?, ?)""",
        (workspace_id, now, now),
    )
    row = conn.execute(
        "SELECT * FROM workspace_subscriptions WHERE workspace_id=?", (workspace_id,),
    ).fetchone()
    return subscription_to_api(row)


def update_subscription_from_provider(
    conn,
    workspace_id: int,
    *,
    provider: str,
    provider_customer_id: str | None = None,
    provider_subscription_id: str | None = None,
    plan: str | None = None,
    status: str | None = None,
    current_period_end: str | None = None,
) -> dict:
    ensure_workspace_subscription(conn, workspace_id)
    updates = ["updated_at=?"]
    params: list = [_now()]
    if provider:
        updates.append("provider=?")
        params.append(provider)
    if provider_customer_id is not None:
        updates.append("provider_customer_id=?")
        params.append(provider_customer_id)
    if provider_subscription_id is not None:
        updates.append("provider_subscription_id=?")
        params.append(provider_subscription_id)
    if plan:
        updates.append("plan=?")
        params.append(plan)
    if status and status in SUBSCRIPTION_STATUSES:
        updates.append("status=?")
        params.append(status)
    if current_period_end is not None:
        updates.append("current_period_end=?")
        params.append(current_period_end)
    params.append(workspace_id)
    conn.execute(
        f"UPDATE workspace_subscriptions SET {', '.join(updates)} WHERE workspace_id=?",
        params,
    )
    row = conn.execute(
        "SELECT * FROM workspace_subscriptions WHERE workspace_id=?", (workspace_id,),
    ).fetchone()
    return subscription_to_api(row)


def subscription_to_api(row) -> dict:
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "provider": row["provider"],
        "provider_customer_id": row["provider_customer_id"],
        "provider_subscription_id": row["provider_subscription_id"],
        "plan": row["plan"],
        "status": row["status"],
        "current_period_end": row["current_period_end"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "is_active": row["status"] in ("active", "trialing"),
    }
