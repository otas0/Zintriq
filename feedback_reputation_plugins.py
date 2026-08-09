"""Reputation platform plugins — integration layer for external review sources."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime


class FeedbackReputationPlugin(ABC):
    slug: str = ""
    name: str = ""
    capabilities: tuple[str, ...] = ()

    @abstractmethod
    def connect(self, conn, user_id: int, credentials: dict) -> dict:
        ...

    @abstractmethod
    def disconnect(self, conn, connection_id: int) -> None:
        ...

    @abstractmethod
    def sync_feedback(self, conn, *, workspace_id: int, connection_id: int) -> dict:
        ...

    @abstractmethod
    def get_rating(self, conn, connection_id: int) -> dict | None:
        ...

    def get_capabilities(self) -> list[str]:
        return list(self.capabilities)


class StubReputationPlugin(FeedbackReputationPlugin):
    """Base stub — OAuth/sync implemented when platform credentials are available."""

    def connect(self, conn, user_id: int, credentials: dict) -> dict:
        return {"status": "connected", "note": "Plugin registered — OAuth pending"}

    def disconnect(self, conn, connection_id: int) -> None:
        conn.execute(
            "UPDATE user_integration_connections SET status='disconnected', updated_at=? WHERE id=?",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), connection_id),
        )

    def sync_feedback(self, conn, *, workspace_id: int, connection_id: int) -> dict:
        return {"synced": 0, "platform": self.slug}

    def get_rating(self, conn, connection_id: int) -> dict | None:
        return None


class GoogleBusinessPlugin(StubReputationPlugin):
    slug = "google_business"
    name = "Google Business Profile"
    capabilities = ("read_reviews", "reply_reviews", "read_rating")


class YelpPlugin(StubReputationPlugin):
    slug = "yelp"
    name = "Yelp"
    capabilities = ("read_reviews", "read_rating")


class TripadvisorPlugin(StubReputationPlugin):
    slug = "tripadvisor"
    name = "Tripadvisor"
    capabilities = ("read_reviews", "read_rating")


class TablelogPlugin(StubReputationPlugin):
    slug = "tablelog"
    name = "Tablelog"
    capabilities = ("read_reviews", "reservation_feedback")


class OpenTablePlugin(StubReputationPlugin):
    slug = "opentable"
    name = "OpenTable"
    capabilities = ("read_reviews", "read_rating")


PLUGIN_REGISTRY: dict[str, FeedbackReputationPlugin] = {
    p.slug: p for p in (
        GoogleBusinessPlugin(), YelpPlugin(), TripadvisorPlugin(),
        TablelogPlugin(), OpenTablePlugin(),
    )
}


def upsert_external_feedback(
    conn,
    *,
    workspace_id: int,
    store_id: int,
    platform: str,
    external_id: str,
    rating: int | None,
    content: str,
    customer_name: str = "",
) -> int:
    """Map external review into Feedback Core with deduplication."""
    mapping = conn.execute(
        "SELECT feedback_id FROM external_feedback_mappings WHERE platform=? AND external_id=?",
        (platform, external_id),
    ).fetchone()
    if mapping:
        return int(mapping["feedback_id"])
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """INSERT INTO feedback_records
           (store_id, workspace_id, feedback_type, source_type, source,
            external_platform, external_id, rating, comment, customer_name, status, updated_at)
           VALUES (?, ?, 'review', ?, ?, ?, ?, ?, ?, ?, 'new', ?)""",
        (store_id, workspace_id, platform, platform, platform, external_id, rating, content, customer_name, now),
    )
    fid = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO external_feedback_mappings
           (feedback_id, platform, external_id, sync_status, last_synced_at)
           VALUES (?, ?, ?, 'synced', ?)""",
        (fid, platform, external_id, now),
    )
    return fid
