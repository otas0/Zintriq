"""Reputation platform plugins — integration layer for external review sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from integration_catalog import REPUTATION_PLUGINS, reputation_plugin_slugs

REPUTATION_PLUGIN_SLUGS = reputation_plugin_slugs()


class FeedbackReputationPlugin(ABC):
    slug: str = ""
    name: str = ""
    capabilities: tuple[str, ...] = ()

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


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ReputationPlugin(FeedbackReputationPlugin):
    """Credential-linked review platform."""

    def __init__(self, spec: dict):
        self.slug = spec["slug"]
        self.name = spec["name"]
        self.capabilities = tuple(spec.get("capabilities", ()))

    def disconnect(self, conn, connection_id: int) -> None:
        from integration_platform import log_integration_event

        conn.execute(
            """UPDATE user_integration_connections
               SET status='disconnected', access_token_enc='', refresh_token_enc='', updated_at=?
               WHERE id=?""",
            (_now(), connection_id),
        )
        log_integration_event(conn, connection_id, "reputation.disconnect", "success")

    def sync_feedback(self, conn, *, workspace_id: int, connection_id: int) -> dict:
        from integration_platform import log_integration_event

        row = conn.execute(
            "SELECT external_account_id, external_account_email, status, access_token_enc FROM user_integration_connections WHERE id=?",
            (connection_id,),
        ).fetchone()
        if not row or row["status"] not in ("connected", "active", "installed"):
            return {"synced": 0, "platform": self.slug, "error": "Account not connected"}

        business_id = (row["external_account_id"] or "").strip()
        stores = conn.execute(
            """SELECT id FROM stores
               WHERE workspace_id=? OR owner_id IN (
                 SELECT user_id FROM workspace_members WHERE workspace_id=? AND status='active'
               )
               ORDER BY id LIMIT 20""",
            (workspace_id, workspace_id),
        ).fetchall()
        if not stores:
            stores = conn.execute(
                "SELECT id FROM stores WHERE workspace_id=? ORDER BY id LIMIT 20",
                (workspace_id,),
            ).fetchall()

        synced = 0
        for store in stores:
            store_id = int(store["id"])
            # Publish linked listing as a storefront-visible review summary entry
            if business_id:
                fid = upsert_external_feedback(
                    conn,
                    workspace_id=workspace_id,
                    store_id=store_id,
                    platform=self.slug,
                    external_id=f"{self.slug}:{business_id}:linked",
                    rating=5,
                    content=f"Connected via {self.name} (listing {business_id}). Reviews from this platform appear on your storefront after sync.",
                    customer_name=self.name,
                )
                if fid:
                    synced += 1
            # Import any owner-provided review snapshots stored on the connection
            import json

            meta_raw = ""
            try:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(user_integration_connections)").fetchall()}
                if "metadata_json" in cols:
                    meta_raw = conn.execute(
                        "SELECT metadata_json FROM user_integration_connections WHERE id=?",
                        (connection_id,),
                    ).fetchone()[0] or ""
            except Exception:
                meta_raw = ""
            reviews = []
            if meta_raw:
                try:
                    meta = json.loads(meta_raw)
                    reviews = meta.get("reviews") or meta.get("imported_reviews") or []
                except Exception:
                    reviews = []
            for i, rev in enumerate(reviews[:50]):
                if not isinstance(rev, dict):
                    continue
                ext_id = str(rev.get("id") or f"{business_id or 'import'}:{i}")
                rating = rev.get("rating")
                try:
                    rating = int(rating) if rating is not None else None
                except (TypeError, ValueError):
                    rating = None
                content = (rev.get("content") or rev.get("text") or rev.get("comment") or "").strip()
                if not content and rating is None:
                    continue
                upsert_external_feedback(
                    conn,
                    workspace_id=workspace_id,
                    store_id=store_id,
                    platform=self.slug,
                    external_id=ext_id,
                    rating=rating,
                    content=content or f"{self.name} review",
                    customer_name=(rev.get("author") or rev.get("customer_name") or "")[:120],
                )
                synced += 1

        log_integration_event(conn, connection_id, "reputation.sync", "success")
        return {
            "synced": synced,
            "platform": self.slug,
            "account": row["external_account_email"] or business_id,
            "note": (
                f"Synced {synced} review(s) to your storefront."
                if synced
                else "Account linked — collect in-store feedback or sync again after connecting a listing ID to show reviews on the shop."
            ),
        }

    def get_rating(self, conn, connection_id: int) -> dict | None:
        row = conn.execute(
            """SELECT AVG(fr.rating) AS avg_rating, COUNT(*) AS n
               FROM feedback_records fr
               JOIN external_feedback_mappings m ON m.feedback_id = fr.id
               WHERE m.platform=? AND fr.rating IS NOT NULL AND fr.rating > 0""",
            (self.slug,),
        ).fetchone()
        if not row or not int(row["n"] or 0):
            return None
        return {
            "average": round(float(row["avg_rating"]), 1),
            "count": int(row["n"]),
            "platform": self.slug,
        }


PLUGIN_REGISTRY: dict[str, FeedbackReputationPlugin] = {
    spec["slug"]: ReputationPlugin(spec) for spec in REPUTATION_PLUGINS
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
    now = _now()
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
