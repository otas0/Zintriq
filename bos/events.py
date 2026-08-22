"""Zintriq Event Bus — centralized domain event backbone.

Every significant business action emits an immutable, append-only domain event.
Platforms subscribe via in-process handlers; modules never call each other directly.

Human spec: docs/bos/EVENT_BUS.md
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

# Standard lifecycle verbs — combined with object_type → e.g. customer.created
STANDARD_VERBS = frozenset({
    "created", "updated", "archived", "restored", "deleted",
    "assigned", "published", "completed", "cancelled",
    "submitted", "replied", "viewed", "joined", "scanned", "imported",
    "invited", "removed",
})

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS domain_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id INTEGER NOT NULL,
    workspace_id INTEGER,
    store_id INTEGER,
    user_id INTEGER,
    actor TEXT DEFAULT 'system',
    title TEXT NOT NULL,
    detail TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    href TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_domain_events_workspace
    ON domain_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_domain_events_object
    ON domain_events(object_type, object_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_domain_events_type
    ON domain_events(event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS event_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    priority TEXT DEFAULT 'info',
    object_type TEXT,
    object_id INTEGER,
    href TEXT,
    read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_event_notifications_user
    ON event_notifications(user_id, read, created_at DESC);

CREATE TABLE IF NOT EXISTS event_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    metric_key TEXT NOT NULL,
    metric_value REAL NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, metric_key)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _event_id() -> str:
    return secrets.token_hex(16)


@dataclass
class DomainEvent:
    event_id: str
    event_type: str
    object_type: str
    object_id: int
    workspace_id: int | None = None
    store_id: int | None = None
    user_id: int | None = None
    actor: str = "system"
    title: str = ""
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    href: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "workspace_id": self.workspace_id,
            "store_id": self.store_id,
            "user_id": self.user_id,
            "actor": self.actor,
            "title": self.title,
            "detail": self.detail,
            "metadata": self.metadata,
            "href": self.href,
            "created_at": self.created_at,
        }


# In-process subscribers — platforms react here without direct module coupling.
_subscribers: list[Callable[[sqlite3.Connection, DomainEvent], None]] = []


def subscribe(handler: Callable[[sqlite3.Connection, DomainEvent], None]) -> None:
    _subscribers.append(handler)


def init_event_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)


def resolve_workspace_id(conn: sqlite3.Connection, *, workspace_id=None, store_id=None, owner_id=None) -> int | None:
    if workspace_id:
        return int(workspace_id)
    if store_id:
        row = conn.execute("SELECT workspace_id FROM stores WHERE id=?", (store_id,)).fetchone()
        if row and row["workspace_id"]:
            return int(row["workspace_id"])
    if owner_id:
        row = conn.execute(
            """SELECT w.id FROM workspaces w
               JOIN organizations o ON o.id = w.organization_id
               WHERE o.owner_id = ? ORDER BY w.id LIMIT 1""",
            (owner_id,),
        ).fetchone()
        if row:
            return int(row["id"])
    return None


def workspace_member_ids(conn: sqlite3.Connection, workspace_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT user_id FROM workspace_members WHERE workspace_id=? AND status='active'",
        (workspace_id,),
    ).fetchall()
    return [int(r["user_id"]) for r in rows]


def emit(
    conn: sqlite3.Connection,
    event_type: str,
    object_type: str,
    object_id: int,
    *,
    workspace_id: int | None = None,
    store_id: int | None = None,
    user_id: int | None = None,
    owner_id: int | None = None,
    actor: str = "system",
    title: str = "",
    detail: str = "",
    metadata: dict[str, Any] | None = None,
    href: str | None = None,
) -> str:
    """Emit a domain event. Immutable, append-only. Returns event_id."""
    ws_id = resolve_workspace_id(conn, workspace_id=workspace_id, store_id=store_id, owner_id=owner_id)
    eid = _event_id()
    meta = metadata or {}
    created = _now()

    conn.execute(
        """INSERT INTO domain_events
           (event_id, event_type, object_type, object_id, workspace_id, store_id,
            user_id, actor, title, detail, metadata, href, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            eid, event_type, object_type, object_id, ws_id, store_id,
            user_id, actor, title, detail, json.dumps(meta), href, created,
        ),
    )

    event = DomainEvent(
        event_id=eid,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        workspace_id=ws_id,
        store_id=store_id,
        user_id=user_id,
        actor=actor,
        title=title,
        detail=detail,
        metadata=meta,
        href=href,
        created_at=created,
    )

    for handler in _subscribers:
        try:
            handler(conn, event)
        except Exception:
            pass  # subscribers must not break emit

    return eid


def event_type(object_type: str, verb: str) -> str:
    return f"{object_type}.{verb}"


# ── Subscribers ──────────────────────────────────────────────────────────────


def _subscriber_notifications(conn: sqlite3.Connection, event: DomainEvent) -> None:
    """Notification platform — reacts to events, never triggered by modules directly."""
    if not event.workspace_id:
        return

    notify_rules: dict[str, tuple[str, str, str]] = {
        "feedback.submitted": ("New feedback received", event.detail or "A customer submitted feedback", "info"),
        "customer.created": ("New customer", event.title or "Customer joined", "info"),
        "customer.joined": ("New customer", event.title or "Customer joined", "info"),
        "workspace.created": ("Workspace created", event.title, "success"),
        "order.completed": ("Order completed", event.title, "success"),
        "member.invited": ("Member invited", event.title or "A new invitation was sent", "info"),
        "member.joined": ("Invitation accepted", event.title or "A member joined the workspace", "success"),
        "member.invitation_cancelled": ("Invitation cancelled", event.title, "info"),
        "member.removed": ("Member removed", event.title, "warning"),
        "member.role_updated": ("Role updated", event.title, "info"),
        "workspace.ownership_transferred": ("Ownership transferred", event.title, "warning"),
        "task.created": ("New task", event.title or "Task created", "info"),
        "task.assigned": ("Task assigned", event.title, "info"),
        "task.completed": ("Task completed", event.title, "success"),
        "task.archived": ("Task archived", event.title, "info"),
        "task.comment_added": ("Task comment", event.title, "info"),
    }

    rule = notify_rules.get(event.event_type)
    if not rule and event.event_type.startswith("feedback."):
        if event.metadata.get("rating") is not None and int(event.metadata.get("rating") or 5) <= 2:
            rule = ("Negative feedback", event.title or "Low rating received", "warning")

    if not rule:
        return

    title, body, priority = rule
    member_ids = workspace_member_ids(conn, event.workspace_id)
    if event.user_id and event.user_id in member_ids:
        targets = [event.user_id]
    else:
        targets = member_ids or ([event.user_id] if event.user_id else [])

    for uid in targets:
        conn.execute(
            """INSERT INTO event_notifications
               (event_id, user_id, title, body, priority, object_type, object_id, href)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.event_id, uid, title, body, priority, event.object_type, event.object_id, event.href),
        )


def _subscriber_analytics(conn: sqlite3.Connection, event: DomainEvent) -> None:
    """Analytics platform — consume-only counters from events."""
    if not event.workspace_id:
        return

    counters: dict[str, float] = {}
    if event.event_type in ("customer.created", "customer.joined"):
        counters["customers_total"] = 1
    elif event.event_type == "feedback.submitted":
        counters["feedback_total"] = 1
        rating = event.metadata.get("rating")
        if rating is not None:
            conn.execute(
                """INSERT INTO event_analytics (workspace_id, metric_key, metric_value, updated_at)
                   VALUES (?, 'feedback_rating_sum', ?, ?)
                   ON CONFLICT(workspace_id, metric_key) DO UPDATE SET
                     metric_value = metric_value + excluded.metric_value,
                     updated_at = excluded.updated_at""",
                (event.workspace_id, float(rating), _now()),
            )
            conn.execute(
                """INSERT INTO event_analytics (workspace_id, metric_key, metric_value, updated_at)
                   VALUES (?, 'feedback_rating_count', 1, ?)
                   ON CONFLICT(workspace_id, metric_key) DO UPDATE SET
                     metric_value = metric_value + 1,
                     updated_at = excluded.updated_at""",
                (event.workspace_id, _now()),
            )
    elif event.event_type == "order.completed":
        amount = float(event.metadata.get("amount") or 0)
        if amount:
            counters["revenue_total"] = amount

    for key, delta in counters.items():
        conn.execute(
            """INSERT INTO event_analytics (workspace_id, metric_key, metric_value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(workspace_id, metric_key) DO UPDATE SET
                 metric_value = metric_value + excluded.metric_value,
                 updated_at = excluded.updated_at""",
            (event.workspace_id, key, delta, _now()),
        )


def _subscriber_customer_timeline(conn: sqlite3.Connection, event: DomainEvent) -> None:
    """Customer timeline — assembled from related events."""
    customer_id = event.metadata.get("customer_id")
    owner_id = event.metadata.get("owner_id") or event.user_id

    if event.object_type == "customer":
        customer_id = event.object_id

    if not customer_id or not owner_id:
        return

    # Mirror into customer_activities for existing timeline UI (read-only projection).
    activity_map = {
        "customer.created": "joined",
        "customer.joined": "joined",
        "customer.updated": "updated",
        "customer.archived": "archived",
        "feedback.submitted": "feedback",
        "event.attended": "event",
        "appointment.completed": "appointment",
        "order.completed": "purchase",
        "qr.scanned": "visit",
        "check_in.created": "check_in",
        "check_in.completed": "check_in",
        "check_in.arrived": "check_in",
    }
    activity_type = activity_map.get(event.event_type, event.event_type.split(".")[-1])

    conn.execute(
        """INSERT INTO customer_activities
           (customer_id, owner_id, store_id, activity_type, title, detail,
            related_object_type, related_object_id, source, actor)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            int(customer_id), int(owner_id), event.store_id, activity_type,
            event.title, event.detail, event.object_type, event.object_id,
            event.event_type.split(".")[0], event.actor,
        ),
    )
    conn.execute(
        "UPDATE customer_profiles SET last_activity_at=?, updated_at=? WHERE id=?",
        (_now(), _now(), int(customer_id)),
    )


def _subscriber_workspace_activity(conn: sqlite3.Connection, event: DomainEvent) -> None:
    """Activity feed projection for workspace timeline."""
    if not event.workspace_id:
        return
    if event.object_type == "customer" and event.event_type.startswith("customer."):
        return

    workspace_prefixes = ("workspace.", "store.", "feedback.", "member.", "product.", "task.", "booking.", "check_in.", "qr_experience.")
    if not any(event.event_type.startswith(p) for p in workspace_prefixes):
        return

    conn.execute(
        """INSERT INTO workspace_activity
           (workspace_id, actor_id, object_type, object_id, action, title, detail)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            event.workspace_id, event.user_id, event.object_type, event.object_id,
            event.event_type.split(".")[-1], event.title, event.detail,
        ),
    )


def register_default_subscribers() -> None:
    """Wire platform subscribers — call once at startup."""
    for handler in (
        _subscriber_notifications,
        _subscriber_analytics,
        _subscriber_customer_timeline,
        _subscriber_workspace_activity,
    ):
        if handler not in _subscribers:
            subscribe(handler)
