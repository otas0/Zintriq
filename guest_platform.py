"""Guest identity — visitor_key, recent stores (My Places), inquiry binding."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from datetime import datetime
from typing import Any

GUEST_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS guest_store_visits (
    visitor_key TEXT NOT NULL,
    store_id INTEGER NOT NULL,
    visit_count INTEGER NOT NULL DEFAULT 1,
    first_visited_at TEXT NOT NULL,
    last_visited_at TEXT NOT NULL,
    last_path TEXT,
    PRIMARY KEY (visitor_key, store_id),
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_guest_visits_recent
    ON guest_store_visits(visitor_key, last_visited_at DESC);

CREATE TABLE IF NOT EXISTS guest_visitor_profiles (
    visitor_key TEXT PRIMARY KEY,
    display_name TEXT,
    email TEXT,
    phone TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guest_email_identities (
    email TEXT PRIMARY KEY COLLATE NOCASE,
    visitor_key TEXT NOT NULL UNIQUE,
    linked_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guest_remember_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL COLLATE NOCASE,
    visitor_key TEXT NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_guest_remember_tokens_email
    ON guest_remember_tokens(email);
"""

GUEST_REMEMBER_TTL_MINUTES = 15


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _db_retry(fn, *, attempts: int = 8):
    for attempt in range(attempts):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= attempts - 1:
                raise
            time.sleep(min(0.05 * (2**attempt), 1.0))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    normalized = email.strip().lower()
    return normalized or None


def migrate_guest_tables(conn) -> None:
    conn.executescript(GUEST_SCHEMA_SQL)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(store_inquiries)")}
    if "customer_id" not in columns:
        conn.execute("ALTER TABLE store_inquiries ADD COLUMN customer_id INTEGER")


def ensure_visitor_key(flask_session) -> str:
    """Shared anonymous guest id — storefront, QR experiences, inquiries."""
    key = flask_session.get("visitor_key")
    if not key:
        key = secrets.token_urlsafe(16)
        flask_session["visitor_key"] = key
    return key


def is_storefront_shell_path(path: str) -> bool:
    """Customer store pages use a minimal in-store header (not hub/marketing nav)."""
    return path.startswith("/store/")


def is_customer_surface_path(path: str) -> bool:
    if path == "/home" or path == "/account" or path.startswith("/account/"):
        return True
    if path == "/venues" or path.startswith("/help"):
        return True
    return path.startswith(
        ("/store/", "/places", "/place/", "/discover", "/e/", "/guest/", "/qr/")
    )


def is_customer_hub_path(path: str) -> bool:
    """Shell with side/bottom nav — home, places, account, help."""
    if path == "/home" or path == "/account" or path.startswith("/help"):
        return True
    if path == "/places" or path.startswith("/places/"):
        return True
    return False


def customer_nav_tab(path: str) -> str | None:
    """Bottom tab highlight for in-store customer shell."""
    if path == "/home":
        return "home"
    if path == "/places" or path.startswith("/places/"):
        return "places"
    if path == "/account":
        return "account"
    return None


def guest_remembered_email(conn, visitor_key: str) -> str | None:
    if not visitor_key:
        return None
    row = conn.execute(
        "SELECT email FROM guest_email_identities WHERE visitor_key = ?",
        (visitor_key,),
    ).fetchone()
    return row["email"] if row else None


def upsert_guest_profile(
    conn,
    visitor_key: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> None:
    if not visitor_key:
        return
    name = (display_name or "").strip() or None
    email_n = _normalize_email(email)
    phone_n = (phone or "").strip() or None
    if not (name or email_n or phone_n):
        return
    existing = conn.execute(
        "SELECT display_name, email, phone FROM guest_visitor_profiles WHERE visitor_key = ?",
        (visitor_key,),
    ).fetchone()
    now = _now()
    if existing:
        conn.execute(
            """UPDATE guest_visitor_profiles
               SET display_name = COALESCE(?, display_name),
                   email = COALESCE(?, email),
                   phone = COALESCE(?, phone),
                   updated_at = ?
               WHERE visitor_key = ?""",
            (name, email_n, phone_n, now, visitor_key),
        )
    else:
        conn.execute(
            """INSERT INTO guest_visitor_profiles (visitor_key, display_name, email, phone, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (visitor_key, name, email_n, phone_n, now),
        )


def merge_visitor_keys(conn, target: str, source: str) -> str:
    """Merge guest visits + profile from source into target visitor_key."""
    if not target:
        return source or ""
    if not source or target == source:
        return target

    source_visits = conn.execute(
        "SELECT * FROM guest_store_visits WHERE visitor_key = ?",
        (source,),
    ).fetchall()
    for visit in source_visits:
        existing = conn.execute(
            "SELECT * FROM guest_store_visits WHERE visitor_key = ? AND store_id = ?",
            (target, visit["store_id"]),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE guest_store_visits
                   SET visit_count = visit_count + ?,
                       last_visited_at = CASE WHEN ? > last_visited_at THEN ? ELSE last_visited_at END,
                       first_visited_at = CASE WHEN ? < first_visited_at THEN ? ELSE first_visited_at END,
                       last_path = COALESCE(?, last_path)
                   WHERE visitor_key = ? AND store_id = ?""",
                (
                    int(visit["visit_count"] or 1),
                    visit["last_visited_at"],
                    visit["last_visited_at"],
                    visit["first_visited_at"],
                    visit["first_visited_at"],
                    visit["last_path"],
                    target,
                    visit["store_id"],
                ),
            )
        else:
            conn.execute(
                """INSERT INTO guest_store_visits
                   (visitor_key, store_id, visit_count, first_visited_at, last_visited_at, last_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    target,
                    visit["store_id"],
                    visit["visit_count"],
                    visit["first_visited_at"],
                    visit["last_visited_at"],
                    visit["last_path"],
                ),
            )
    conn.execute("DELETE FROM guest_store_visits WHERE visitor_key = ?", (source,))

    source_profile = conn.execute(
        "SELECT display_name, email, phone FROM guest_visitor_profiles WHERE visitor_key = ?",
        (source,),
    ).fetchone()
    if source_profile:
        upsert_guest_profile(
            conn,
            target,
            display_name=source_profile["display_name"],
            email=source_profile["email"],
            phone=source_profile["phone"],
        )
        conn.execute("DELETE FROM guest_visitor_profiles WHERE visitor_key = ?", (source,))

    return target


def link_guest_email(conn, email: str, visitor_key: str) -> None:
    email_n = _normalize_email(email)
    if not email_n or not visitor_key:
        return
    now = _now()
    conn.execute(
        """INSERT INTO guest_email_identities (email, visitor_key, linked_at, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(email) DO UPDATE SET
             visitor_key = excluded.visitor_key,
             updated_at = excluded.updated_at""",
        (email_n, visitor_key, now, now),
    )
    upsert_guest_profile(conn, visitor_key, email=email_n)


def create_guest_remember_token(conn, email: str, visitor_key: str) -> str:
    email_n = _normalize_email(email)
    if not email_n or not visitor_key:
        raise ValueError("email and visitor_key required")
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM guest_remember_tokens WHERE email = ?", (email_n,))
    conn.execute(
        """INSERT INTO guest_remember_tokens (email, visitor_key, token_hash, expires_at)
           VALUES (?, ?, ?, datetime('now', ?))""",
        (email_n, visitor_key, _hash_token(token), f"+{GUEST_REMEMBER_TTL_MINUTES} minutes"),
    )
    return token


def consume_guest_remember_token(conn, token: str):
    row = conn.execute(
        """SELECT * FROM guest_remember_tokens
           WHERE token_hash = ? AND expires_at > datetime('now')""",
        (_hash_token(token),),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM guest_remember_tokens WHERE id = ?", (row["id"],))
    return row


def apply_guest_remember_link(conn, token_row, current_visitor_key: str) -> str:
    """Restore guest identity from magic link — merge visits into canonical visitor_key."""
    email = token_row["email"]
    token_key = token_row["visitor_key"]
    existing = conn.execute(
        "SELECT visitor_key FROM guest_email_identities WHERE email = ?",
        (email,),
    ).fetchone()

    if existing:
        canonical = existing["visitor_key"]
    else:
        canonical = token_key or current_visitor_key

    if token_key and token_key != canonical:
        merge_visitor_keys(conn, canonical, token_key)
    if current_visitor_key and current_visitor_key != canonical:
        merge_visitor_keys(conn, canonical, current_visitor_key)

    link_guest_email(conn, email, canonical)
    return canonical


def send_guest_remember_email(link: str, email: str) -> bool:
    """Email magic link when SMTP is configured."""
    from email_delivery import send_transactional_email

    subject = "Save your Zintriq places"
    text = (
        "Open this link on any device to restore shops you've visited on Zintriq.\n\n"
        f"{link}\n\n"
        "This link expires in 15 minutes. If you didn't request it, you can ignore this email."
    )
    html = (
        "<p>Open this link on any device to restore shops you've visited on Zintriq.</p>"
        f'<p><a href="{link}">{link}</a></p>'
        "<p>This link expires in 15 minutes. If you didn't request it, you can ignore this email.</p>"
    )
    return send_transactional_email(email, subject, text, html_body=html)


def record_store_visit(
    conn,
    visitor_key: str,
    store_id: int,
    *,
    path: str | None = None,
) -> None:
    if not visitor_key or not store_id:
        return
    now = _now()

    def _write() -> None:
        existing = conn.execute(
            "SELECT visit_count FROM guest_store_visits WHERE visitor_key = ? AND store_id = ?",
            (visitor_key, store_id),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE guest_store_visits
                   SET visit_count = visit_count + 1, last_visited_at = ?, last_path = ?
                   WHERE visitor_key = ? AND store_id = ?""",
                (now, path, visitor_key, store_id),
            )
        else:
            conn.execute(
                """INSERT INTO guest_store_visits
                   (visitor_key, store_id, visit_count, first_visited_at, last_visited_at, last_path)
                   VALUES (?, ?, 1, ?, ?, ?)""",
                (visitor_key, store_id, now, now, path),
            )

    _db_retry(_write)


def recent_store_count(conn, visitor_key: str) -> int:
    if not visitor_key:
        return 0
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM guest_store_visits v
           JOIN stores s ON s.id = v.store_id
           WHERE v.visitor_key = ? AND COALESCE(s.status, 'active') != 'archived'""",
        (visitor_key,),
    ).fetchone()
    return int(row["c"] or 0)


def recent_stores_for_visitor(conn, visitor_key: str, *, limit: int = 10) -> list[dict[str, Any]]:
    if not visitor_key:
        return []
    from storefront_platform import build_store_profile

    rows = conn.execute(
        """SELECT v.*, s.slug, s.name, s.description, s.logo_url, s.background_image, s.status
           FROM guest_store_visits v
           JOIN stores s ON s.id = v.store_id
           WHERE v.visitor_key = ? AND COALESCE(s.status, 'active') != 'archived'
           ORDER BY v.last_visited_at DESC
           LIMIT ?""",
        (visitor_key, limit),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        store_row = conn.execute("SELECT * FROM stores WHERE id = ?", (row["store_id"],)).fetchone()
        profile = build_store_profile(conn, dict(store_row)) if store_row else {"hours": {}, "logo_url": None}
        hours = profile["hours"]
        out.append({
            "store_id": row["store_id"],
            "slug": row["slug"],
            "name": row["name"],
            "logo_url": profile.get("logo_url") or (row["logo_url"] if "logo_url" in row.keys() else None),
            "description": (row["description"] or "")[:120] or None,
            "visit_count": int(row["visit_count"] or 1),
            "last_visited_at": row["last_visited_at"],
            "is_open": hours.get("is_open"),
            "hours_line": hours.get("status_line") or hours.get("legacy_text"),
            "storefront_url": f"/store/{row['slug']}",
        })
    return out


def guest_contact_hints(conn, visitor_key: str) -> dict[str, str]:
    if not visitor_key:
        return {}
    row = conn.execute(
        "SELECT display_name, email, phone FROM guest_visitor_profiles WHERE visitor_key = ?",
        (visitor_key,),
    ).fetchone()
    if not row:
        return {}
    hints: dict[str, str] = {}
    if row["display_name"]:
        hints["customer_name"] = row["display_name"]
    if row["email"]:
        hints["customer_email"] = row["email"]
    if row["phone"]:
        hints["customer_phone"] = row["phone"]
    return hints


def bind_inquiry_to_guest(
    conn,
    visitor_key: str,
    store: dict | Any,
    *,
    customer_name: str,
    customer_email: str | None = None,
    customer_phone: str | None = None,
    inquiry_id: int | None = None,
) -> int | None:
    """Link inquiry to guest profile + owner CRM customer record."""
    from customer_platform import find_or_create_customer, log_customer_activity

    upsert_guest_profile(
        conn,
        visitor_key,
        display_name=customer_name,
        email=customer_email,
        phone=customer_phone,
    )

    owner_id = store.get("owner_id") if isinstance(store, dict) else store["owner_id"]
    store_id = store.get("id") if isinstance(store, dict) else store["id"]
    if not owner_id:
        return None

    customer_id = find_or_create_customer(
        conn,
        int(owner_id),
        email=customer_email,
        phone=customer_phone,
        full_name=customer_name,
        store_id=int(store_id),
        source="storefront_inquiry",
    )
    if customer_id and inquiry_id:
        conn.execute(
            "UPDATE store_inquiries SET customer_id = ? WHERE id = ? AND store_id = ?",
            (customer_id, inquiry_id, store_id),
        )
        log_customer_activity(
            conn,
            customer_id,
            int(owner_id),
            "visit",
            f"Store inquiry — {_store_field(store, 'name')}",
            detail=(customer_email or customer_phone or "")[:200],
            store_id=int(store_id),
            related_object_type="store_inquiry",
            related_object_id=inquiry_id,
            source="storefront",
            actor="customer",
        )
    return customer_id


def _store_field(store: dict | Any, key: str, default=None):
    if isinstance(store, dict):
        return store.get(key, default)
    try:
        return store[key]
    except (KeyError, TypeError):
        return default


def sibling_stores_for_hub(conn, store: dict | Any) -> tuple[list, str, str]:
    """Active sibling stores + display brand name + scope (workspace|owner)."""
    store_id = int(_store_field(store, "id"))
    workspace_id = _store_field(store, "workspace_id")
    owner_id = _store_field(store, "owner_id")
    brand_name = (_store_field(store, "owner_name") or "").strip() or None
    scope = "owner"
    rows: list = []

    if workspace_id:
        ws = conn.execute("SELECT name FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if ws and ws["name"]:
            brand_name = ws["name"]
        rows = conn.execute(
            """SELECT * FROM stores
               WHERE workspace_id = ? AND id != ?
                 AND COALESCE(status, 'active') != 'archived'
               ORDER BY name COLLATE NOCASE""",
            (workspace_id, store_id),
        ).fetchall()
        if rows:
            scope = "workspace"

    if not rows and owner_id:
        rows = conn.execute(
            """SELECT * FROM stores
               WHERE owner_id = ? AND id != ?
                 AND COALESCE(status, 'active') != 'archived'
               ORDER BY name COLLATE NOCASE""",
            (owner_id, store_id),
        ).fetchall()
        scope = "owner"

    if not brand_name:
        brand_name = "Our locations"

    return [dict(r) for r in rows], brand_name, scope


def brand_hub_for_store(conn, store: dict | Any) -> dict[str, Any] | None:
    """Brand hub — other locations under same workspace or owner."""
    siblings, brand_name, scope = sibling_stores_for_hub(conn, store)
    if not siblings:
        return None

    from storefront_platform import build_store_profile, format_distance_km, haversine_km

    current_lat = _store_field(store, "latitude")
    current_lng = _store_field(store, "longitude")
    try:
        origin_lat = float(current_lat) if current_lat is not None else None
        origin_lng = float(current_lng) if current_lng is not None else None
    except (TypeError, ValueError):
        origin_lat = origin_lng = None

    locations: list[dict[str, Any]] = []
    for row in siblings:
        profile = build_store_profile(conn, row)
        hours = profile["hours"]
        lat = row.get("latitude") if isinstance(row, dict) else row["latitude"]
        lng = row.get("longitude") if isinstance(row, dict) else row["longitude"]
        distance_km = None
        distance_label = None
        if origin_lat is not None and origin_lng is not None and lat is not None and lng is not None:
            try:
                distance_km = haversine_km(origin_lat, origin_lng, float(lat), float(lng))
                distance_label = format_distance_km(distance_km)
            except (TypeError, ValueError):
                pass
        locations.append({
            "store_id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "logo_url": profile.get("logo_url"),
            "address": profile.get("address"),
            "is_open": hours.get("is_open"),
            "hours_line": hours.get("status_line") or hours.get("legacy_text"),
            "lat": lat,
            "lng": lng,
            "distance_km": distance_km,
            "distance_label": distance_label,
        })

    if origin_lat is not None and origin_lng is not None:
        locations.sort(key=lambda loc: (loc["distance_km"] is None, loc["distance_km"] if loc["distance_km"] is not None else 9999))

    return {
        "brand_name": brand_name,
        "scope": scope,
        "locations": locations,
    }
