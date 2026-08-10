"""Place directory — venue QR, tenant store listings."""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any

PLACE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    cover_image TEXT,
    address TEXT,
    owner_id INTEGER NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(owner_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_places_owner ON places(owner_id, status);

CREATE TABLE IF NOT EXISTS place_stores (
    place_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    unit_label TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (place_id, store_id),
    FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE CASCADE,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_place_stores_order ON place_stores(place_id, sort_order);

CREATE TABLE IF NOT EXISTS place_analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    store_id INTEGER,
    metadata TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE CASCADE,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_place_events_place ON place_analytics_events(place_id, created_at DESC);

CREATE TABLE IF NOT EXISTS place_tenant_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    applicant_user_id INTEGER NOT NULL,
    unit_label TEXT,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    rejection_note TEXT,
    reviewed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE CASCADE,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE,
    FOREIGN KEY(applicant_user_id) REFERENCES users(id),
    UNIQUE(place_id, store_id)
);
CREATE INDEX IF NOT EXISTS idx_place_apps_status ON place_tenant_applications(place_id, status);
"""

PLACE_EVENT_TYPES = ("place_view", "tenant_click")
APPLICATION_STATUSES = ("pending", "approved", "rejected")


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def migrate_place_tables(conn) -> None:
    conn.executescript(PLACE_SCHEMA_SQL)


def unique_place_slug(conn, base: str | None = None) -> str:
    seed = (base or secrets.token_urlsafe(6)).lower()
    seed = "".join(ch for ch in seed if ch.isalnum())[:24] or secrets.token_urlsafe(6).replace("-", "")[:8]
    slug = seed
    n = 0
    while conn.execute("SELECT 1 FROM places WHERE slug = ?", (slug,)).fetchone():
        n += 1
        slug = f"{seed[:20]}{n}"[:24]
    return slug


def list_places_for_owner(conn, owner_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT p.*,
                  (SELECT COUNT(*) FROM place_stores ps WHERE ps.place_id = p.id) AS tenant_count,
                  (SELECT COUNT(*) FROM place_tenant_applications a
                   WHERE a.place_id = p.id AND a.status = 'pending') AS pending_applications
           FROM places p
           WHERE p.owner_id = ?
           ORDER BY p.updated_at DESC, p.created_at DESC""",
        (owner_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_place_by_slug(conn, slug: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM places WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def require_place_owner(place: dict | Any, user_id: int) -> None:
    owner_id = place.get("owner_id") if isinstance(place, dict) else place["owner_id"]
    if int(owner_id) != int(user_id):
        from flask import abort

        abort(403)


def create_place(
    conn,
    owner_id: int,
    *,
    name: str,
    description: str | None = None,
    address: str | None = None,
    cover_image: str | None = None,
    slug: str | None = None,
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("name required")
    place_slug = unique_place_slug(conn, slug or name.replace(" ", "-"))
    now = _now()
    cur = conn.execute(
        """INSERT INTO places (slug, name, description, cover_image, address, owner_id, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
        (
            place_slug,
            name,
            (description or "").strip() or None,
            (cover_image or "").strip() or None,
            (address or "").strip() or None,
            owner_id,
            now,
            now,
        ),
    )
    place_id = int(cur.lastrowid)
    row = conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    return dict(row)


def update_place(
    conn,
    place_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    address: str | None = None,
    cover_image: str | None = None,
    status: str | None = None,
) -> None:
    fields: list[str] = []
    params: list[Any] = []
    if name is not None:
        fields.append("name = ?")
        params.append(name.strip())
    if description is not None:
        fields.append("description = ?")
        params.append(description.strip() or None)
    if address is not None:
        fields.append("address = ?")
        params.append(address.strip() or None)
    if cover_image is not None:
        fields.append("cover_image = ?")
        params.append(cover_image.strip() or None)
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if not fields:
        return
    fields.append("updated_at = ?")
    params.append(_now())
    params.append(place_id)
    conn.execute(f"UPDATE places SET {', '.join(fields)} WHERE id = ?", params)


def is_place_tenant(conn, place_id: int, store_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM place_stores WHERE place_id = ? AND store_id = ?",
        (place_id, store_id),
    ).fetchone()
    return bool(row)


def add_place_tenant(
    conn,
    place_id: int,
    store_id: int,
    *,
    unit_label: str | None = None,
) -> bool:
    store_row = conn.execute("SELECT status FROM stores WHERE id = ?", (store_id,)).fetchone()
    if not store_row or (store_row["status"] or "active") == "archived":
        return False
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) AS m FROM place_stores WHERE place_id = ?",
        (place_id,),
    ).fetchone()["m"]
    try:
        conn.execute(
            """INSERT INTO place_stores (place_id, store_id, unit_label, sort_order)
               VALUES (?, ?, ?, ?)""",
            (place_id, store_id, (unit_label or "").strip() or None, int(max_order) + 1),
        )
        conn.execute(
            """UPDATE place_tenant_applications
               SET status = 'approved', reviewed_at = ?, updated_at = ?, rejection_note = NULL
               WHERE place_id = ? AND store_id = ? AND status = 'pending'""",
            (_now(), _now(), place_id, store_id),
        )
        conn.execute("UPDATE places SET updated_at = ? WHERE id = ?", (_now(), place_id))
        return True
    except Exception:
        return False


def remove_place_tenant(conn, place_id: int, store_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM place_stores WHERE place_id = ? AND store_id = ?",
        (place_id, store_id),
    )
    if cur.rowcount:
        conn.execute("UPDATE places SET updated_at = ? WHERE id = ?", (_now(), place_id))
        return True
    return False


def tenants_for_place(conn, place_id: int, *, public_only: bool = False) -> list[dict[str, Any]]:
    from storefront_platform import build_store_profile

    rows = conn.execute(
        """SELECT ps.unit_label, ps.sort_order, s.*
           FROM place_stores ps
           JOIN stores s ON s.id = ps.store_id
           WHERE ps.place_id = ?
           ORDER BY ps.sort_order ASC, s.name COLLATE NOCASE ASC""",
        (place_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        if public_only and (row["status"] or "active") == "archived":
            continue
        profile = build_store_profile(conn, dict(row))
        hours = profile["hours"]
        out.append({
            "store_id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "description": (row["description"] or "")[:140] or None,
            "logo_url": profile.get("logo_url"),
            "unit_label": row["unit_label"],
            "is_open": hours.get("is_open"),
            "hours_line": hours.get("status_line") or hours.get("legacy_text"),
            "storefront_url": f"/store/{row['slug']}",
        })
    return out


def record_place_event(
    conn,
    place_id: int,
    event_type: str,
    *,
    store_id: int | None = None,
    metadata: dict | None = None,
) -> None:
    if event_type not in PLACE_EVENT_TYPES:
        return
    conn.execute(
        """INSERT INTO place_analytics_events (place_id, event_type, store_id, metadata)
           VALUES (?, ?, ?, ?)""",
        (place_id, event_type, store_id, json.dumps(metadata or {})),
    )


def place_insights(conn, place_id: int, *, period: str = "30d") -> dict[str, Any]:
    from storefront_platform import analytics_period_clause

    clause, params = analytics_period_clause(period, column="created_at")
    views = conn.execute(
        f"""SELECT COUNT(*) AS c FROM place_analytics_events
            WHERE place_id = ? AND event_type = 'place_view' AND {clause}""",
        [place_id, *params],
    ).fetchone()
    clicks = conn.execute(
        f"""SELECT COUNT(*) AS c FROM place_analytics_events
            WHERE place_id = ? AND event_type = 'tenant_click' AND {clause}""",
        [place_id, *params],
    ).fetchone()
    click_clause, click_params = analytics_period_clause(period, column="e.created_at")
    top_tenants = conn.execute(
        f"""SELECT e.store_id, s.name, COUNT(*) AS clicks
            FROM place_analytics_events e
            LEFT JOIN stores s ON s.id = e.store_id
            WHERE e.place_id = ? AND e.event_type = 'tenant_click' AND {click_clause}
            GROUP BY e.store_id ORDER BY clicks DESC LIMIT 5""",
        [place_id, *click_params],
    ).fetchall()

    app_clause, app_params = analytics_period_clause(period, column="created_at")
    submitted_row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM place_tenant_applications
            WHERE place_id = ? AND {app_clause}""",
        [place_id, *app_params],
    ).fetchone()
    reviewed_clause, reviewed_params = analytics_period_clause(period, column="reviewed_at")
    approved_row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM place_tenant_applications
            WHERE place_id = ? AND status = 'approved' AND {reviewed_clause}""",
        [place_id, *reviewed_params],
    ).fetchone()
    rejected_row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM place_tenant_applications
            WHERE place_id = ? AND status = 'rejected' AND {reviewed_clause}""",
        [place_id, *reviewed_params],
    ).fetchone()
    submitted = int(submitted_row["c"] or 0)
    approved = int(approved_row["c"] or 0)
    rejected = int(rejected_row["c"] or 0)
    decided = approved + rejected
    approval_rate = round((approved / decided) * 100) if decided else None

    return {
        "period": period,
        "views": int(views["c"] or 0),
        "tenant_clicks": int(clicks["c"] or 0),
        "top_tenants": [dict(r) for r in top_tenants],
        "applications_submitted": submitted,
        "applications_approved": approved,
        "applications_rejected": rejected,
        "applications_pending": pending_application_count(conn, place_id),
        "application_approval_rate": approval_rate,
    }


def resolve_store_for_tenant(conn, store_slug: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM stores WHERE slug = ? AND COALESCE(status, 'active') != 'archived'",
        (store_slug.strip().lower(),),
    ).fetchone()
    return dict(row) if row else None


def stores_owned_by_user(conn, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT id, slug, name, status FROM stores
           WHERE owner_id = ? AND COALESCE(status, 'active') != 'archived'
           ORDER BY name COLLATE NOCASE""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def tenant_application_for_store(conn, place_id: int, store_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM place_tenant_applications WHERE place_id = ? AND store_id = ?",
        (place_id, store_id),
    ).fetchone()
    return dict(row) if row else None


def submit_tenant_application(
    conn,
    place_id: int,
    store_id: int,
    applicant_user_id: int,
    *,
    unit_label: str | None = None,
    message: str | None = None,
) -> tuple[str, int | None]:
    """Returns (result_code, application_id). result_code: submitted|updated|already_listed|pending."""
    store = conn.execute("SELECT owner_id, status FROM stores WHERE id = ?", (store_id,)).fetchone()
    if not store or int(store["owner_id"]) != int(applicant_user_id):
        return "forbidden", None
    if (store["status"] or "active") == "archived":
        return "invalid_store", None
    if is_place_tenant(conn, place_id, store_id):
        return "already_listed", None

    unit = (unit_label or "").strip() or None
    msg = (message or "").strip() or None
    now = _now()
    existing = tenant_application_for_store(conn, place_id, store_id)
    if existing:
        if existing["status"] == "pending":
            conn.execute(
                """UPDATE place_tenant_applications
                   SET unit_label = ?, message = ?, updated_at = ?
                   WHERE id = ?""",
                (unit, msg, now, existing["id"]),
            )
            return "updated", int(existing["id"])
        if existing["status"] == "approved":
            return "already_listed", int(existing["id"])
        conn.execute(
            """UPDATE place_tenant_applications
               SET status = 'pending', unit_label = ?, message = ?, rejection_note = NULL,
                   reviewed_at = NULL, updated_at = ?, applicant_user_id = ?
               WHERE id = ?""",
            (unit, msg, now, applicant_user_id, existing["id"]),
        )
        return "submitted", int(existing["id"])

    cur = conn.execute(
        """INSERT INTO place_tenant_applications
           (place_id, store_id, applicant_user_id, unit_label, message, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (place_id, store_id, applicant_user_id, unit, msg, now, now),
    )
    conn.execute("UPDATE places SET updated_at = ? WHERE id = ?", (now, place_id))
    return "submitted", int(cur.lastrowid)


def applications_for_place(
    conn,
    place_id: int,
    *,
    status: str | None = "pending",
) -> list[dict[str, Any]]:
    query = """
        SELECT a.*, s.slug AS store_slug, s.name AS store_name, u.email AS applicant_email
        FROM place_tenant_applications a
        JOIN stores s ON s.id = a.store_id
        JOIN users u ON u.id = a.applicant_user_id
        WHERE a.place_id = ?
    """
    params: list[Any] = [place_id]
    if status:
        query += " AND a.status = ?"
        params.append(status)
    query += " ORDER BY a.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def applications_for_store(conn, store_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT a.*, p.slug AS place_slug, p.name AS place_name
           FROM place_tenant_applications a
           JOIN places p ON p.id = a.place_id
           WHERE a.store_id = ?
           ORDER BY a.updated_at DESC, a.created_at DESC""",
        (store_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def approve_tenant_application(conn, application_id: int, place_owner_id: int) -> bool:
    app_row = conn.execute(
        """SELECT a.*, p.owner_id AS place_owner_id
           FROM place_tenant_applications a
           JOIN places p ON p.id = a.place_id
           WHERE a.id = ?""",
        (application_id,),
    ).fetchone()
    if not app_row or int(app_row["place_owner_id"]) != int(place_owner_id):
        return False
    if app_row["status"] != "pending":
        return False
    if not add_place_tenant(
        conn,
        int(app_row["place_id"]),
        int(app_row["store_id"]),
        unit_label=app_row["unit_label"],
    ):
        if is_place_tenant(conn, int(app_row["place_id"]), int(app_row["store_id"])):
            now = _now()
            conn.execute(
                """UPDATE place_tenant_applications
                   SET status = 'approved', reviewed_at = ?, updated_at = ?
                   WHERE id = ?""",
                (now, now, application_id),
            )
            return True
        return False
    now = _now()
    conn.execute(
        """UPDATE place_tenant_applications
           SET status = 'approved', reviewed_at = ?, updated_at = ?, rejection_note = NULL
           WHERE id = ?""",
        (now, now, application_id),
    )
    return True


def reject_tenant_application(
    conn,
    application_id: int,
    place_owner_id: int,
    *,
    note: str | None = None,
) -> bool:
    app_row = conn.execute(
        """SELECT a.*, p.owner_id AS place_owner_id
           FROM place_tenant_applications a
           JOIN places p ON p.id = a.place_id
           WHERE a.id = ?""",
        (application_id,),
    ).fetchone()
    if not app_row or int(app_row["place_owner_id"]) != int(place_owner_id):
        return False
    if app_row["status"] != "pending":
        return False
    now = _now()
    conn.execute(
        """UPDATE place_tenant_applications
           SET status = 'rejected', rejection_note = ?, reviewed_at = ?, updated_at = ?
           WHERE id = ?""",
        ((note or "").strip() or None, now, now, application_id),
    )
    return True


def pending_application_count(conn, place_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM place_tenant_applications WHERE place_id = ? AND status = 'pending'",
        (place_id,),
    ).fetchone()
    return int(row["c"] or 0)


def application_email_context(conn, application_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT a.*, s.name AS store_name, s.slug AS store_slug,
                  p.name AS place_name, p.slug AS place_slug,
                  u.email AS applicant_email,
                  vo.email AS venue_email
           FROM place_tenant_applications a
           JOIN stores s ON s.id = a.store_id
           JOIN places p ON p.id = a.place_id
           JOIN users u ON u.id = a.applicant_user_id
           JOIN users vo ON vo.id = p.owner_id
           WHERE a.id = ?""",
        (application_id,),
    ).fetchone()
    return dict(row) if row else None


def notify_venue_new_application(conn, application_id: int, *, review_url: str) -> bool:
    from email_delivery import send_transactional_email

    ctx = application_email_context(conn, application_id)
    if not ctx or not ctx.get("venue_email"):
        return False
    subject = f"New tenant application — {ctx['store_name']}"
    text = (
        f"{ctx['store_name']} applied to list in {ctx['place_name']}.\n\n"
        f"Unit: {ctx.get('unit_label') or '—'}\n"
        f"Note: {ctx.get('message') or '—'}\n\n"
        f"Review: {review_url}\n"
    )
    html = (
        f"<p><strong>{ctx['store_name']}</strong> applied to list in <strong>{ctx['place_name']}</strong>.</p>"
        f"<p>Unit: {ctx.get('unit_label') or '—'}<br>Note: {ctx.get('message') or '—'}</p>"
        f'<p><a href="{review_url}">Review application</a></p>'
    )
    return send_transactional_email(ctx["venue_email"], subject, text, html_body=html)


def notify_tenant_application_decision(
    conn,
    application_id: int,
    *,
    approved: bool,
    directory_url: str | None = None,
) -> bool:
    from email_delivery import send_transactional_email

    ctx = application_email_context(conn, application_id)
    if not ctx or not ctx.get("applicant_email"):
        return False
    place_name = ctx["place_name"]
    if approved:
        subject = f"Approved — listed in {place_name}"
        text = (
            f"Your shop {ctx['store_name']} is now listed in {place_name}.\n\n"
            f"Directory: {directory_url or ''}\n"
        )
        html = (
            f"<p>Your shop <strong>{ctx['store_name']}</strong> is now listed in <strong>{place_name}</strong>.</p>"
            + (f'<p><a href="{directory_url}">View directory</a></p>' if directory_url else "")
        )
    else:
        reason = ctx.get("rejection_note") or "No reason provided."
        subject = f"Application update — {place_name}"
        text = (
            f"Your application for {ctx['store_name']} at {place_name} was not approved.\n\n"
            f"Reason: {reason}\n\n"
            "You can submit a new application from the place directory."
        )
        html = (
            f"<p>Your application for <strong>{ctx['store_name']}</strong> at <strong>{place_name}</strong> "
            "was not approved.</p>"
            f"<p>Reason: {reason}</p>"
            "<p>You can submit a new application from the place directory.</p>"
        )
    return send_transactional_email(ctx["applicant_email"], subject, text, html_body=html)
