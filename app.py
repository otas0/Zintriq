from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import secrets
import socket
import sqlite3
import time
from functools import wraps
from pathlib import Path

import qrcode
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials
except ImportError:
    firebase_admin = firebase_auth = credentials = None


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "marketqr.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"


def _load_local_env() -> None:
    """Load KEY=VALUE lines from .env.local without overwriting existing env."""
    path = BASE_DIR / ".env.local"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ[key] = value


_load_local_env()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def init_db() -> None:
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL COLLATE NOCASE, password_hash TEXT NOT NULL, firebase_uid TEXT UNIQUE, two_factor_secret TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS auth_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, purpose TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id));
            CREATE TABLE IF NOT EXISTS stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                owner_name TEXT,
                contact TEXT,
                description TEXT,
                owner_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                description TEXT,
                image_url TEXT,
                FOREIGN KEY(store_id) REFERENCES stores(id)
            );
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(stores)")}
        if "owner_id" not in columns:
            conn.execute("ALTER TABLE stores ADD COLUMN owner_id INTEGER")
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "two_factor_secret" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN two_factor_secret TEXT")
        if "firebase_uid" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN firebase_uid TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_firebase_uid_unique ON users(firebase_uid) WHERE firebase_uid IS NOT NULL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS store_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(owner_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS qr_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                name TEXT,
                code TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(store_id) REFERENCES stores(id)
            );
            CREATE TABLE IF NOT EXISTS item_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                display_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(store_id) REFERENCES stores(id)
            );
            CREATE TABLE IF NOT EXISTS store_labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(owner_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS store_label_assignments (
                store_id INTEGER NOT NULL,
                label_id INTEGER NOT NULL,
                PRIMARY KEY (store_id, label_id),
                FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE,
                FOREIGN KEY(label_id) REFERENCES store_labels(id) ON DELETE CASCADE
            );
        """)
        store_columns = {row["name"] for row in conn.execute("PRAGMA table_info(stores)")}
        for column, definition in (
            ("address", "TEXT"),
            ("business_hours", "TEXT"),
            ("background_image", "TEXT"),
            ("status", "TEXT DEFAULT 'active'"),
            ("group_id", "INTEGER"),
            ("updated_at", "TEXT"),
        ):
            if column not in store_columns:
                conn.execute(f"ALTER TABLE stores ADD COLUMN {column} {definition}")
        from storefront_platform import migrate_storefront_columns
        migrate_storefront_columns(conn)
        store_columns = {row["name"] for row in conn.execute("PRAGMA table_info(stores)")}
        item_columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
        for column, definition in (
            ("group_id", "INTEGER"),
            ("sku", "TEXT"),
            ("inventory", "INTEGER"),
            ("display_order", "INTEGER DEFAULT 0"),
            ("status", "TEXT DEFAULT 'published'"),
            ("internal_notes", "TEXT"),
            ("updated_at", "TEXT"),
        ):
            if column not in item_columns:
                conn.execute(f"ALTER TABLE items ADD COLUMN {column} {definition}")
        for store in conn.execute("SELECT id FROM stores").fetchall():
            exists = conn.execute("SELECT 1 FROM qr_codes WHERE store_id = ?", (store["id"],)).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO qr_codes (store_id, name, code) VALUES (?, ?, ?)",
                    (store["id"], "Default", secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10].lower()),
                )
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                FOREIGN KEY(owner_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                type TEXT DEFAULT 'general',
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                UNIQUE(organization_id, slug),
                FOREIGN KEY(organization_id) REFERENCES organizations(id)
            );
        """)
        if "workspace_id" not in store_columns:
            conn.execute("ALTER TABLE stores ADD COLUMN workspace_id INTEGER")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                cover_image TEXT,
                description TEXT,
                event_date TEXT,
                start_time TEXT,
                end_time TEXT,
                timezone TEXT DEFAULT 'Asia/Singapore',
                venue TEXT,
                capacity INTEGER DEFAULT 100,
                status TEXT DEFAULT 'draft',
                internal_notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS event_attendees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                pass_code TEXT UNIQUE NOT NULL,
                pass_status TEXT DEFAULT 'valid',
                checked_in_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS pass_scan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attendee_id INTEGER NOT NULL,
                result TEXT NOT NULL,
                scanned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(attendee_id) REFERENCES event_attendees(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS business_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                card_code TEXT UNIQUE NOT NULL,
                profile_photo TEXT,
                name TEXT NOT NULL,
                position TEXT,
                company TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                address TEXT,
                social_links TEXT,
                biography TEXT,
                company_logo TEXT,
                group_name TEXT,
                status TEXT DEFAULT 'published',
                scan_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS qr_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                product_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                image_url TEXT,
                description TEXT,
                sku TEXT,
                brand TEXT,
                category TEXT,
                specifications TEXT,
                user_manual_url TEXT,
                warranty_info TEXT,
                status TEXT DEFAULT 'published',
                scan_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS check_in_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                point_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                location TEXT,
                description TEXT,
                active_status TEXT DEFAULT 'active',
                opening_hours TEXT,
                notes TEXT,
                scenario TEXT DEFAULT 'visitor',
                status TEXT DEFAULT 'published',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS check_in_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                point_id INTEGER NOT NULL,
                result TEXT NOT NULL,
                location TEXT,
                scanned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(point_id) REFERENCES check_in_points(id) ON DELETE CASCADE
            );
        """)
        qr_columns = {row["name"] for row in conn.execute("PRAGMA table_info(qr_codes)")}
        if "pass_type" not in qr_columns:
            conn.execute("ALTER TABLE qr_codes ADD COLUMN pass_type TEXT DEFAULT 'storefront'")
        if "ref_id" not in qr_columns:
            conn.execute("ALTER TABLE qr_codes ADD COLUMN ref_id INTEGER")
        from feedback_platform import init_feedback_tables
        init_feedback_tables(conn)
        from customer_platform import init_customer_tables
        init_customer_tables(conn)
        from workspace_platform import init_workspace_tables
        init_workspace_tables(conn)
        from bos.events import init_event_tables
        init_event_tables(conn)
        from bos.workflows import init_workflow_tables
        init_workflow_tables(conn)
        from bos_modules_platform import init_bos_modules_tables
        init_bos_modules_tables(conn)
        from team_platform import init_team_tables
        init_team_tables(conn)
        from task_platform import init_task_tables
        init_task_tables(conn)
        from contact_platform import init_contact_tables
        init_contact_tables(conn)
        from booking_platform import init_booking_tables
        init_booking_tables(conn)
        from checkin_platform import init_checkin_tables
        init_checkin_tables(conn)
        from calendar_platform import init_calendar_tables
        init_calendar_tables(conn)
        from integration_platform import init_integration_tables
        init_integration_tables(conn)
        from integrations import init_integrations_core_tables
        init_integrations_core_tables(conn)
        from feedback_core_platform import init_feedback_core_tables
        init_feedback_core_tables(conn)
        from qr_experience_platform import init_qr_experience_tables
        init_qr_experience_tables(conn)
        from bos.mvp_schema import init_mvp_schema
        init_mvp_schema(conn)


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def current_user():
    if not session.get("user_id"):
        return None
    with db() as conn:
        return conn.execute("SELECT id, email FROM users WHERE id = ?", (session["user_id"],)).fetchone()


@app.context_processor
def inject_globals():
    path = request.path
    if path.startswith("/app"):
        active_app_nav = "bos"
    elif path.startswith("/my-stores") or path.startswith("/manage") or path.startswith("/create"):
        active_app_nav = "qr"
    else:
        active_app_nav = None
    return {"csrf_token": csrf_token, "current_user": current_user(), "active_app_nav": active_app_nav}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please sign in to manage a storefront.", "error")
            return redirect(url_for("login", next=request.path))
        try:
            with db() as conn:
                from team_platform import touch_user_presence
                touch_user_presence(conn, user["id"])
        except Exception:
            pass
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def protect_forms():
    if request.method != "POST":
        return
    if request.path == "/api/integrations/google-calendar/webhook":
        return
    if request.path.startswith("/api/integrations/webhooks/"):
        return
    submitted = (
        request.form.get("csrf_token", "")
        or request.headers.get("X-CSRF-Token", "")
        or (request.get_json(silent=True) or {}).get("csrf_token", "")
    )
    expected = session.get("csrf_token")
    if not expected or not secrets.compare_digest(submitted, expected):
        abort(400, "Invalid form token. Please refresh and try again.")


def get_store_or_404(slug: str):
    with db() as conn:
        store = conn.execute("SELECT * FROM stores WHERE slug = ?", (slug,)).fetchone()
    if not store:
        abort(404)
    return store


def require_store_owner(store):
    if not current_user() or store["owner_id"] != current_user()["id"]:
        abort(403)


def public_store_or_404(slug: str):
    store = get_store_or_404(slug)
    if store["status"] == "archived":
        abort(404)
    return store


def storefront_render_context(
    store,
    *,
    preview_mode: bool,
    group_filter: str | None = None,
    view: str = "shop",
    group_in_url: bool = False,
):
    from storefront_platform import active_deals_for_storefront, build_store_profile, deals_map_for_items

    view = "deals" if view == "deals" else "shop"
    group_nav = build_item_group_nav(store["id"], published_only=True)
    show_group_nav = len(group_nav) > 1

    with db() as conn:
        store_profile = build_store_profile(conn, store)
        deals = active_deals_for_storefront(conn, store["id"])
        deals_map = deals_map_for_items(conn, store["id"])

    catalog_sections: list[dict] = []
    active_group = None
    active_group_name = None
    items: list = []

    if view == "deals":
        all_published = customer_items(store["id"], None)
        deal_items = [item for item in all_published if item["id"] in deals_map]
        items = deal_items
        if deal_items:
            catalog_sections = [{"id": "deals", "num": "", "name": "Deals", "items": deal_items}]
        active_group_name = "Deals"
    elif group_in_url and group_nav:
        active_group, _, _, active_group_name = resolve_item_group_context(
            store["id"], group_filter, published_only=True
        )
        items = customer_items(store["id"], active_group)
        if items:
            idx = next((i for i, g in enumerate(group_nav, 1) if g["id"] == active_group), 1)
            catalog_sections = [{
                "id": active_group,
                "num": f"{idx:02d}",
                "name": active_group_name,
                "items": items,
            }]
    elif group_nav:
        for idx, entry in enumerate(group_nav, 1):
            section_items = customer_items(store["id"], entry["id"])
            if section_items:
                catalog_sections.append({
                    "id": entry["id"],
                    "num": f"{idx:02d}",
                    "name": entry["name"],
                    "items": section_items,
                })
        items = catalog_sections[0]["items"] if catalog_sections else []
        active_group_name = "Shop"
    else:
        items = customer_items(store["id"], None)
        if items:
            catalog_sections = [{"id": "all", "num": "01", "name": "Available now", "items": items}]
        active_group_name = "Available now"

    return {
        "store": store,
        "store_profile": store_profile,
        "items": items,
        "catalog_sections": catalog_sections,
        "deals": deals,
        "deals_map": deals_map,
        "store_view": view,
        "group_nav": group_nav,
        "show_group_nav": show_group_nav,
        "active_group": active_group,
        "active_group_name": active_group_name,
        "preview_mode": preview_mode,
        "group_in_url": group_in_url,
    }


def get_item_or_404(store_id: int, item_id: int):
    with db() as conn:
        item = conn.execute("SELECT * FROM items WHERE id = ? AND store_id = ?", (item_id, store_id)).fetchone()
    if not item:
        abort(404)
    return item


def owner_items(store_id: int, group_id: str | int | None = None):
    query = "SELECT items.*, item_groups.name AS group_name FROM items LEFT JOIN item_groups ON items.group_id = item_groups.id WHERE items.store_id = ?"
    params: list = [store_id]
    if group_id == "default":
        query += " AND items.group_id IS NULL"
    elif group_id is not None:
        query += " AND items.group_id = ?"
        params.append(group_id)
    query += " ORDER BY items.display_order, items.id DESC"
    with db() as conn:
        return conn.execute(query, params).fetchall()


def customer_items(store_id: int, group_id: str | int | None = None):
    query = "SELECT items.*, item_groups.name AS group_name FROM items LEFT JOIN item_groups ON items.group_id = item_groups.id WHERE items.store_id = ? AND items.status = 'published'"
    params: list = [store_id]
    if group_id == "default":
        query += " AND items.group_id IS NULL"
    elif group_id is not None:
        query += " AND items.group_id = ?"
        params.append(group_id)
    query += " ORDER BY items.display_order, items.id DESC"
    with db() as conn:
        return conn.execute(query, params).fetchall()


def store_qr_codes(store_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM qr_codes WHERE store_id = ? ORDER BY id", (store_id,)).fetchall()


def store_item_groups(store_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM item_groups WHERE store_id = ? ORDER BY display_order, id", (store_id,)).fetchall()


def count_items_in_group(store_id: int, group_id: str | int, published_only: bool = False) -> int:
    with db() as conn:
        if group_id == "default":
            query = "SELECT COUNT(*) AS total FROM items WHERE store_id = ? AND group_id IS NULL"
            params: list = [store_id]
        else:
            query = "SELECT COUNT(*) AS total FROM items WHERE store_id = ? AND group_id = ?"
            params = [store_id, group_id]
        if published_only:
            query += " AND status = 'published'"
        return conn.execute(query, params).fetchone()["total"]


def build_item_group_nav(store_id: int, published_only: bool = False) -> list[dict]:
    groups = store_item_groups(store_id)
    if not groups:
        return []
    nav: list[dict] = []
    if count_items_in_group(store_id, "default", published_only) > 0:
        nav.append({"id": "default", "name": "Default"})
    for group in groups:
        nav.append({"id": group["id"], "name": group["name"]})
    return nav


def parse_item_group_arg(raw: str | None) -> str | int | None:
    if raw is None:
        return None
    if raw == "default":
        return "default"
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def resolve_item_group_context(store_id: int, raw: str | None, published_only: bool = False) -> tuple[str | int | None, list[dict], bool, str | None]:
    nav = build_item_group_nav(store_id, published_only)
    if not nav:
        return None, [], False, None
    parsed = parse_item_group_arg(raw)
    valid_ids = {entry["id"] for entry in nav}
    active = parsed if parsed in valid_ids else nav[0]["id"]
    active_name = next(entry["name"] for entry in nav if entry["id"] == active)
    return active, nav, True, active_name


def group_query_param(group_id: str | int) -> str:
    return "default" if group_id == "default" else str(group_id)


def owner_store_groups(owner_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM store_groups WHERE owner_id = ? ORDER BY name", (owner_id,)).fetchall()


def save_uploaded_image(field: str) -> str | None:
    upload = request.files.get(field)
    if not upload or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise ValueError("Use a JPG, PNG, WEBP, or GIF image.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(8)}{suffix}"
    upload.save(UPLOAD_DIR / filename)
    return url_for("static", filename=f"uploads/{filename}")


def resolve_image_field(url_field: str, file_field: str, existing: str | None = None) -> str | None:
    uploaded = save_uploaded_image(file_field)
    if uploaded:
        return uploaded
    url = request.form.get(url_field, "").strip()
    if url:
        return url
    return existing


def new_qr_code() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10].lower()


def unique_pass_code(conn) -> str:
    return unique_entity_code(conn, "event_attendees", "pass_code")


def unique_entity_code(conn, table: str, column: str) -> str:
    allowed = {
        ("event_attendees", "pass_code"),
        ("business_cards", "card_code"),
        ("qr_products", "product_code"),
        ("check_in_points", "point_code"),
        ("qr_codes", "code"),
        ("feedback_forms", "form_code"),
        ("feedback_publications", "pub_code"),
    }
    if (table, column) not in allowed:
        raise ValueError("Invalid code table")
    for _ in range(20):
        code = new_qr_code()
        exists = conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (code,)).fetchone()
        if not exists:
            return code
    return secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:12].lower()


EVENT_STATUSES = ("draft", "published", "ongoing", "completed", "archived", "cancelled")
PASS_STATUSES = ("valid", "used", "expired", "cancelled", "invalid")
QR_ENTITY_STATUSES = ("draft", "published", "archived")
CHECKIN_SCENARIOS = (
    ("visitor", "Visitor check-in"),
    ("appointment", "Appointment check-in"),
    ("customer", "Customer arrival"),
    ("employee", "Employee check-in"),
    ("meeting", "Meeting check-in"),
    ("service", "Service check-in"),
    ("internal", "Internal operations"),
)


def parse_social_links(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        links = {}
        for line in raw.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                links[key.strip().lower()] = value.strip()
        return links


def social_links_from_form() -> str:
    links = {}
    for key in ("linkedin", "twitter", "instagram", "facebook", "youtube", "tiktok", "other"):
        value = request.form.get(f"social_{key}", "").strip()
        if value:
            links[key] = value
    return json.dumps(links) if links else ""


def entity_qr_payload(endpoint: str, code: str) -> dict:
    url = public_url_for(endpoint, code=code)
    return {"url": url, "image": qr_data_uri(url)}


def increment_scan_count(table: str, entity_id: int) -> None:
    allowed = {"business_cards", "qr_products", "check_in_points"}
    if table not in allowed:
        return
    with db() as conn:
        conn.execute(
            f"UPDATE {table} SET scan_count = COALESCE(scan_count, 0) + 1 WHERE id = ?",
            (entity_id,),
        )


def store_business_cards(store_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM business_cards WHERE store_id = ? ORDER BY name, id DESC",
            (store_id,),
        ).fetchall()


def get_business_card_or_404(store_id: int, card_id: int):
    with db() as conn:
        card = conn.execute(
            "SELECT * FROM business_cards WHERE id = ? AND store_id = ?",
            (card_id, store_id),
        ).fetchone()
    if not card:
        abort(404)
    return card


def business_card_by_code(code: str):
    with db() as conn:
        return conn.execute(
            """SELECT bc.*, s.name AS store_name, s.slug AS store_slug
               FROM business_cards bc JOIN stores s ON s.id = bc.store_id
               WHERE bc.card_code = ?""",
            (code.lower(),),
        ).fetchone()


def store_qr_products(store_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM qr_products WHERE store_id = ? ORDER BY name, id DESC",
            (store_id,),
        ).fetchall()


def get_qr_product_or_404(store_id: int, product_id: int):
    with db() as conn:
        product = conn.execute(
            "SELECT * FROM qr_products WHERE id = ? AND store_id = ?",
            (product_id, store_id),
        ).fetchone()
    if not product:
        abort(404)
    return product


def qr_product_by_code(code: str):
    with db() as conn:
        return conn.execute(
            """SELECT qp.*, s.name AS store_name, s.slug AS store_slug
               FROM qr_products qp JOIN stores s ON s.id = qp.store_id
               WHERE qp.product_code = ?""",
            (code.lower(),),
        ).fetchone()


def related_qr_products(store_id: int, category: str | None, exclude_id: int, limit: int = 4):
    if not category:
        return []
    with db() as conn:
        return conn.execute(
            """SELECT * FROM qr_products
               WHERE store_id = ? AND category = ? AND id != ? AND status = 'published'
               ORDER BY id DESC LIMIT ?""",
            (store_id, category, exclude_id, limit),
        ).fetchall()


def store_check_in_points(store_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM check_in_points WHERE store_id = ? ORDER BY name, id DESC",
            (store_id,),
        ).fetchall()


def get_check_in_point_or_404(store_id: int, point_id: int):
    with db() as conn:
        point = conn.execute(
            "SELECT * FROM check_in_points WHERE id = ? AND store_id = ?",
            (point_id, store_id),
        ).fetchone()
    if not point:
        abort(404)
    return point


def check_in_point_by_code(code: str):
    with db() as conn:
        return conn.execute(
            """SELECT cp.*, s.name AS store_name, s.slug AS store_slug
               FROM check_in_points cp JOIN stores s ON s.id = cp.store_id
               WHERE cp.point_code = ?""",
            (code.lower(),),
        ).fetchone()


def check_in_stats(point_id: int) -> dict:
    with db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN result = 'success' THEN 1 ELSE 0 END) AS successful,
                      MAX(scanned_at) AS last_checkin
               FROM check_in_log WHERE point_id = ?""",
            (point_id,),
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "successful": int(row["successful"] or 0),
        "last_checkin": row["last_checkin"],
    }


def check_in_activity(store_id: int, point_id: int | None = None, limit: int = 50):
    query = """SELECT l.*, cp.name AS point_name, cp.location, cp.point_code
               FROM check_in_log l
               JOIN check_in_points cp ON cp.id = l.point_id
               WHERE cp.store_id = ?"""
    params: list = [store_id]
    if point_id:
        query += " AND cp.id = ?"
        params.append(point_id)
    query += " ORDER BY l.scanned_at DESC LIMIT ?"
    params.append(limit)
    with db() as conn:
        return conn.execute(query, params).fetchall()


def log_check_in(point_id: int, result: str, location: str | None = None):
    with db() as conn:
        conn.execute(
            "INSERT INTO check_in_log (point_id, result, location) VALUES (?, ?, ?)",
            (point_id, result, location),
        )


def validate_check_in(code: str) -> dict:
    point = check_in_point_by_code(code)
    if not point:
        return {"result": "invalid", "message": "Check-in point not recognized", "point": None}
    if point["status"] == "archived":
        return {"result": "expired", "message": "Check-in point archived", "point": point}
    if point["status"] == "draft":
        return {"result": "invalid", "message": "Check-in point not published", "point": point}
    if point["active_status"] != "active":
        return {"result": "invalid", "message": "Check-in point inactive", "point": point}
    return {"result": "valid", "message": "Ready to check in", "point": point}


def perform_check_in(code: str) -> dict:
    validation = validate_check_in(code)
    point = validation["point"]
    if validation["result"] != "valid":
        if point:
            log_check_in(point["id"], validation["result"], point["location"])
        return validation
    log_check_in(point["id"], "success", point["location"])
    increment_scan_count("check_in_points", point["id"])
    try:
        with db() as conn:
            from qr_experience_runtime import bridge_legacy_checkin
            bridge_legacy_checkin(conn, point)
    except Exception:
        pass
    validation["message"] = f"Checked in at {point['name']}"
    validation["checked_in"] = True
    validation["time"] = time.strftime("%Y-%m-%d %H:%M")
    return validation


def build_vcard(card) -> str:
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{card['name']}"]
    if card["position"]:
        lines.append(f"TITLE:{card['position']}")
    if card["company"]:
        lines.append(f"ORG:{card['company']}")
    if card["phone"]:
        lines.append(f"TEL;TYPE=CELL:{card['phone']}")
    if card["email"]:
        lines.append(f"EMAIL:{card['email']}")
    if card["website"]:
        lines.append(f"URL:{card['website']}")
    if card["address"]:
        lines.append(f"ADR;TYPE=WORK:;;{card['address']}")
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def regenerate_entity_code(conn, table: str, entity_id: int, store_id: int) -> str:
    column_map = {
        "business_cards": "card_code",
        "qr_products": "product_code",
        "check_in_points": "point_code",
        "feedback_forms": "form_code",
        "feedback_publications": "pub_code",
    }
    column = column_map.get(table)
    if not column:
        raise ValueError("Invalid table")
    code = unique_entity_code(conn, table, column)
    conn.execute(
        f"UPDATE {table} SET {column} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?",
        (code, entity_id, store_id),
    )
    return code


def store_events(store_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM events WHERE store_id = ? ORDER BY event_date DESC, id DESC",
            (store_id,),
        ).fetchall()


def get_event_or_404(store_id: int, event_id: int):
    with db() as conn:
        event = conn.execute(
            "SELECT * FROM events WHERE id = ? AND store_id = ?",
            (event_id, store_id),
        ).fetchone()
    if not event:
        abort(404)
    return event


def event_attendees(event_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM event_attendees WHERE event_id = ? ORDER BY name",
            (event_id,),
        ).fetchall()


def event_stats(event_id: int) -> dict:
    with db() as conn:
        event = conn.execute("SELECT capacity, status FROM events WHERE id = ?", (event_id,)).fetchone()
        row = conn.execute(
            """SELECT COUNT(*) AS registered,
                      SUM(CASE WHEN checked_in_at IS NOT NULL THEN 1 ELSE 0 END) AS checked_in
               FROM event_attendees WHERE event_id = ?""",
            (event_id,),
        ).fetchone()
    capacity = int(event["capacity"] or 0)
    registered = int(row["registered"] or 0)
    checked_in = int(row["checked_in"] or 0)
    remaining = max(capacity - checked_in, 0) if capacity else max(registered - checked_in, 0)
    rate = round((checked_in / registered) * 100) if registered else 0
    return {
        "capacity": capacity,
        "registered": registered,
        "checked_in": checked_in,
        "remaining": remaining,
        "rate": rate,
        "status": event["status"],
    }


def attendee_by_code(code: str):
    with db() as conn:
        return conn.execute(
            """SELECT ea.*, e.name AS event_name, e.cover_image, e.description, e.event_date,
                      e.start_time, e.end_time, e.timezone, e.venue, e.status AS event_status,
                      e.capacity, s.name AS store_name, s.slug AS store_slug
               FROM event_attendees ea
               JOIN events e ON e.id = ea.event_id
               JOIN stores s ON s.id = e.store_id
               WHERE ea.pass_code = ?""",
            (code,),
        ).fetchone()


def log_pass_scan(attendee_id: int, result: str):
    with db() as conn:
        conn.execute(
            "INSERT INTO pass_scan_log (attendee_id, result) VALUES (?, ?)",
            (attendee_id, result),
        )


def validate_event_pass(code: str) -> dict:
    attendee = attendee_by_code(code)
    if not attendee:
        return {"result": "invalid", "message": "Pass not recognized", "attendee": None}
    if attendee["pass_status"] == "cancelled":
        return {"result": "cancelled", "message": "Pass cancelled", "attendee": attendee}
    if attendee["pass_status"] == "expired" or attendee["event_status"] in ("archived", "cancelled", "completed"):
        return {"result": "expired", "message": "Pass expired", "attendee": attendee}
    if attendee["pass_status"] == "used" or attendee["checked_in_at"]:
        return {"result": "used", "message": "Already checked in", "attendee": attendee}
    if attendee["event_status"] == "draft":
        return {"result": "invalid", "message": "Event not published", "attendee": attendee}
    stats = event_stats(attendee["event_id"])
    if stats["capacity"] and stats["checked_in"] >= stats["capacity"]:
        return {"result": "invalid", "message": "Event at capacity", "attendee": attendee}
    return {"result": "valid", "message": "Valid pass", "attendee": attendee}


def link_event_attendee_customer(conn, event_id: int, attendee_id: int, name: str, email: str = "") -> None:
    from customer_platform import find_or_create_customer, log_customer_activity
    event = conn.execute(
        "SELECT e.store_id, s.owner_id FROM events e JOIN stores s ON s.id = e.store_id WHERE e.id = ?",
        (event_id,),
    ).fetchone()
    if not event:
        return
    cid = find_or_create_customer(
        conn, event["owner_id"], email=email, full_name=name,
        store_id=event["store_id"], source="event_pass",
    )
    if cid:
        conn.execute("UPDATE event_attendees SET customer_id = ? WHERE id = ?", (cid, attendee_id))
        log_customer_activity(
            conn, cid, event["owner_id"], "event", "Event pass issued",
            store_id=event["store_id"],
            related_object_type="event_attendee", related_object_id=attendee_id,
            source="event_pass",
        )


def log_event_check_in_customer(conn, attendee_id: int) -> None:
    from customer_platform import log_customer_activity
    row = conn.execute(
        """SELECT ea.customer_id, ea.name, ea.email, e.store_id, s.owner_id, e.name AS event_name
           FROM event_attendees ea
           JOIN events e ON e.id = ea.event_id
           JOIN stores s ON s.id = e.store_id
           WHERE ea.id = ?""",
        (attendee_id,),
    ).fetchone()
    if not row or not row["customer_id"]:
        return
    log_customer_activity(
        conn, row["customer_id"], row["owner_id"], "check_in", f"Checked in — {row['event_name']}",
        store_id=row["store_id"],
        related_object_type="event_attendee", related_object_id=attendee_id,
        source="event_pass", actor="customer",
    )


def check_in_pass(code: str) -> dict:
    validation = validate_event_pass(code)
    attendee = validation["attendee"]
    if attendee:
        log_pass_scan(attendee["id"], validation["result"])
    if validation["result"] != "valid":
        return validation
    with db() as conn:
        conn.execute(
            "UPDATE event_attendees SET pass_status = 'used', checked_in_at = CURRENT_TIMESTAMP WHERE id = ?",
            (attendee["id"],),
        )
        log_event_check_in_customer(conn, attendee["id"])
    validation["message"] = f"Checked in — {attendee['name']}"
    validation["checked_in"] = True
    return validation


def attendee_qr_payload(attendee) -> dict:
    url = public_url_for("event_pass_view", code=attendee["pass_code"])
    return {"url": url, "image": qr_data_uri(url)}


def new_store_slug() -> str:
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8].lower()


def row_to_dict(row) -> dict:
    return dict(row) if row else {}


def owner_store_labels(owner_id: int):
    with db() as conn:
        return conn.execute(
            """SELECT sl.*, COUNT(sla.store_id) AS store_count
               FROM store_labels sl
               LEFT JOIN store_label_assignments sla ON sla.label_id = sl.id
               WHERE sl.owner_id = ?
               GROUP BY sl.id
               ORDER BY sl.name""",
            (owner_id,),
        ).fetchall()


def fetch_group_stats(owner_id: int):
    with db() as conn:
        return conn.execute(
            """SELECT g.id, g.name,
                      COUNT(s.id) AS total,
                      SUM(CASE WHEN s.status = 'active' THEN 1 ELSE 0 END) AS active_count,
                      SUM(CASE WHEN s.status = 'archived' THEN 1 ELSE 0 END) AS archived_count,
                      MAX(COALESCE(s.updated_at, s.created_at)) AS last_updated
               FROM store_groups g
               LEFT JOIN stores s ON s.group_id = g.id AND s.owner_id = ?
               WHERE g.owner_id = ?
               GROUP BY g.id
               ORDER BY g.name""",
            (owner_id, owner_id),
        ).fetchall()


def fetch_workspace_stores(owner_id: int):
    with db() as conn:
        stores = conn.execute(
            """SELECT s.*, g.name AS group_name,
                      (SELECT COUNT(*) FROM items WHERE store_id = s.id) AS item_count,
                      (SELECT GROUP_CONCAT(q.name, ', ') FROM qr_codes q WHERE q.store_id = s.id) AS qr_names
               FROM stores s
               LEFT JOIN store_groups g ON s.group_id = g.id
               WHERE s.owner_id = ?
               ORDER BY COALESCE(s.updated_at, s.created_at) DESC, s.id DESC""",
            (owner_id,),
        ).fetchall()
        label_rows = conn.execute(
            """SELECT sla.store_id, sl.id, sl.name
               FROM store_label_assignments sla
               JOIN store_labels sl ON sla.label_id = sl.id
               WHERE sl.owner_id = ?""",
            (owner_id,),
        ).fetchall()
    labels_by_store: dict[int, list] = {}
    for row in label_rows:
        labels_by_store.setdefault(row["store_id"], []).append({"id": row["id"], "name": row["name"]})
    payload = []
    for store in stores:
        record = row_to_dict(store)
        record["labels"] = labels_by_store.get(store["id"], [])
        record["manage_url"] = url_for("manage_store", slug=store["slug"])
        payload.append(record)
    return payload


def workspace_snapshot(owner_id: int) -> dict:
    groups = [row_to_dict(row) for row in fetch_group_stats(owner_id)]
    labels = [row_to_dict(row) for row in owner_store_labels(owner_id)]
    stores = fetch_workspace_stores(owner_id)
    return {"stores": stores, "groups": groups, "labels": labels}


def owned_store_ids(owner_id: int, store_ids: list[int]) -> list[int]:
    if not store_ids:
        return []
    placeholders = ",".join("?" * len(store_ids))
    with db() as conn:
        rows = conn.execute(
            f"SELECT id FROM stores WHERE owner_id = ? AND id IN ({placeholders})",
            [owner_id, *store_ids],
        ).fetchall()
    return [row["id"] for row in rows]


def duplicate_store_record(conn, store_id: int, owner_id: int) -> int:
    store = conn.execute("SELECT * FROM stores WHERE id = ? AND owner_id = ?", (store_id, owner_id)).fetchone()
    if not store:
        raise ValueError("Store not found")
    slug = new_store_slug()
    cursor = conn.execute(
        """INSERT INTO stores (slug, name, owner_name, contact, description, owner_id, address,
           business_hours, background_image, status, group_id, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (
            slug,
            f"Copy of {store['name']}",
            store["owner_name"],
            store["contact"],
            store["description"],
            owner_id,
            store["address"],
            store["business_hours"],
            store["background_image"],
            store["status"],
            store["group_id"],
        ),
    )
    new_id = cursor.lastrowid
    items = conn.execute("SELECT * FROM items WHERE store_id = ?", (store_id,)).fetchall()
    for item in items:
        conn.execute(
            """INSERT INTO items (store_id, name, price, description, image_url, group_id, sku,
               inventory, display_order, status, internal_notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                new_id,
                item["name"],
                item["price"],
                item["description"],
                item["image_url"],
                item["group_id"],
                item["sku"],
                item["inventory"],
                item["display_order"],
                item["status"],
                item["internal_notes"],
            ),
        )
    for qr in conn.execute("SELECT name FROM qr_codes WHERE store_id = ?", (store_id,)).fetchall():
        conn.execute(
            "INSERT INTO qr_codes (store_id, name, code) VALUES (?, ?, ?)",
            (new_id, qr["name"], new_qr_code()),
        )
    for label in conn.execute(
        "SELECT label_id FROM store_label_assignments WHERE store_id = ?", (store_id,)
    ).fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO store_label_assignments (store_id, label_id) VALUES (?, ?)",
            (new_id, label["label_id"]),
        )
    return new_id


def csrf_valid() -> bool:
    submitted = (
        request.form.get("csrf_token", "")
        or request.headers.get("X-CSRF-Token", "")
        or (request.get_json(silent=True) or {}).get("csrf_token", "")
    )
    expected = session.get("csrf_token")
    return bool(expected and submitted and secrets.compare_digest(submitted, expected))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_auth_token(user_id: int, purpose: str) -> str:
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE user_id = ? AND purpose = ?", (user_id, purpose))
        conn.execute("INSERT INTO auth_tokens (user_id, purpose, token_hash, expires_at) VALUES (?, ?, ?, datetime('now', '+15 minutes'))", (user_id, purpose, hash_token(token)))
    return token


def consume_auth_token(token: str, purpose: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM auth_tokens WHERE token_hash = ? AND purpose = ? AND expires_at > CURRENT_TIMESTAMP", (hash_token(token), purpose)).fetchone()
        if row:
            conn.execute("DELETE FROM auth_tokens WHERE id = ?", (row["id"],))
    return row


def totp_code(secret: str, moment: int | None = None) -> str:
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding)
    counter = int((moment or time.time()) // 30).to_bytes(8, "big")
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7fffffff) % 1_000_000
    return f"{number:06d}"


def valid_totp(secret: str, code: str) -> bool:
    return bool(code.isdigit() and len(code) == 6 and any(secrets.compare_digest(totp_code(secret, time.time() + step * 30), code) for step in (-1, 0, 1)))


def verify_firebase_token(id_token: str):
    """Verify an ID token on the server; never trust browser profile data alone."""
    service_account = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not firebase_admin or not service_account:
        raise RuntimeError("Firebase Admin is not configured")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(service_account))
    return firebase_auth.verify_id_token(id_token, check_revoked=True)


def qr_data_uri(link: str) -> str:
    image = qrcode.make(link)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def public_url_for(endpoint: str, **values) -> str:
    """Absolute URL for QR codes — uses PUBLIC_BASE_URL when set (LAN testing)."""
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    path = url_for(endpoint, **values)
    if base:
        return f"{base}{path}"
    return url_for(endpoint, _external=True, **values)


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


@app.route("/")
def index():
    if current_user():
        return redirect(url_for("bos.store"))
    return render_template("index.html")


def sign_in_user(user_id: int):
    session.clear()
    session["user_id"] = user_id
    csrf_token()


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("bos.store"))
    if request.method == "POST":
        email, password, confirm = request.form.get("email", "").strip().lower(), request.form.get("password", ""), request.form.get("confirm_password", "")
        if "@" not in email or len(email) > 254:
            flash("Enter a valid email address.", "error")
        elif len(password) < 12:
            flash("Use a password with at least 12 characters.", "error")
        elif password != confirm:
            flash("Your passwords do not match.", "error")
        else:
            try:
                with db() as conn:
                    # PBKDF2 is deliberately specified for compatibility with Python/OpenSSL
                    # builds that do not expose hashlib.scrypt.
                    cursor = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                        (email, generate_password_hash(password, method="pbkdf2:sha256:600000")))
                sign_in_user(cursor.lastrowid)
                return redirect(url_for("bos.store"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists. Please sign in.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("bos.store"))
    if request.method == "POST":
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (request.form.get("email", "").strip().lower(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            if user["two_factor_secret"]:
                session["pending_2fa_user_id"] = user["id"]
                return redirect(url_for("two_factor_login"))
            sign_in_user(user["id"])
            destination = request.args.get("next", "")
            return redirect(destination if destination.startswith("/") and not destination.startswith("//") else url_for("bos.store"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.post("/auth/firebase")
def firebase_login():
    payload = request.get_json(silent=True) or {}
    try:
        decoded = verify_firebase_token(payload.get("idToken", ""))
    except Exception:
        return {"error": "Social sign-in is not configured or the sign-in token was invalid."}, 401
    email = (decoded.get("email") or "").strip().lower()
    firebase_uid = decoded.get("uid")
    if not email or not decoded.get("email_verified") or not firebase_uid:
        return {"error": "Your social account needs a verified email address."}, 400
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE firebase_uid = ? OR email = ?", (firebase_uid, email)).fetchone()
        is_new = False
        if user:
            if not user["firebase_uid"]:
                conn.execute("UPDATE users SET firebase_uid = ? WHERE id = ?", (firebase_uid, user["id"]))
        else:
            is_new = True
            cursor = conn.execute("INSERT INTO users (email, password_hash, firebase_uid) VALUES (?, ?, ?)",
                (email, generate_password_hash(secrets.token_urlsafe(32), method="pbkdf2:sha256:600000"), firebase_uid))
            user = conn.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
        from integrations.auth.service import AuthService
        AuthService.link_user(conn, int(user["id"]), {
            "auth_provider": "firebase",
            "auth_provider_id": firebase_uid,
            "email": email,
            "full_name": decoded.get("name") or "",
        })
    if user["two_factor_secret"]:
        session["pending_2fa_user_id"] = user["id"]
        return {"next": url_for("two_factor_login")}
    sign_in_user(user["id"])
    intent = payload.get("intent", "login")
    if is_new and intent == "signup":
        return {"next": url_for("bos.store")}
    return {"next": url_for("bos.store")}


@app.route("/login/2fa", methods=["GET", "POST"])
def two_factor_login():
    user_id = session.get("pending_2fa_user_id")
    if not user_id:
        return redirect(url_for("login"))
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user or not user["two_factor_secret"]:
        session.pop("pending_2fa_user_id", None)
        return redirect(url_for("login"))
    if request.method == "POST":
        if valid_totp(user["two_factor_secret"], request.form.get("code", "").strip()):
            sign_in_user(user["id"])
            return redirect(url_for("bos.store"))
        flash("That verification code is not valid. Try the newest code in your app.", "error")
    return render_template("two_factor_login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        with db() as conn:
            user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token = create_auth_token(user["id"], "reset")
            app.logger.warning("Development password-reset link: %s", url_for("reset_password", token=token, _external=True))
        flash("If that email has an account, a reset link has been sent. In local development, check the Flask terminal for the link.", "success")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    if request.method == "POST":
        password, confirm = request.form.get("password", ""), request.form.get("confirm_password", "")
        if len(password) < 12 or password != confirm:
            flash("Use matching passwords with at least 12 characters.", "error")
        else:
            auth_token = consume_auth_token(token, "reset")
            if not auth_token:
                flash("This reset link is invalid or expired. Request a new one.", "error")
                return redirect(url_for("forgot_password"))
            with db() as conn:
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password, method="pbkdf2:sha256:600000"), auth_token["user_id"]))
            flash("Password changed. You can now sign in.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html", token=token)


@app.route("/magic-link", methods=["GET", "POST"])
def magic_link():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        with db() as conn:
            user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token = create_auth_token(user["id"], "magic")
            app.logger.warning("Development magic-login link: %s", url_for("magic_signin", token=token, _external=True))
        flash("If that email has an account, a sign-in link has been sent. In local development, check the Flask terminal for the link.", "success")
        return redirect(url_for("login"))
    return render_template("magic_link.html")


@app.get("/magic-signin/<token>")
def magic_signin(token: str):
    auth_token = consume_auth_token(token, "magic")
    if not auth_token:
        flash("This sign-in link is invalid or expired. Request a new one.", "error")
        return redirect(url_for("login"))
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (auth_token["user_id"],)).fetchone()
    if user["two_factor_secret"]:
        session["pending_2fa_user_id"] = user["id"]
        return redirect(url_for("two_factor_login"))
    sign_in_user(user["id"])
    return redirect(url_for("bos.store"))


@app.post("/logout")
def logout():
    session.clear(); flash("You have been signed out.", "success")
    return redirect(url_for("index"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = current_user()
    with db() as conn:
        record = conn.execute("SELECT id, email, two_factor_secret FROM users WHERE id = ?", (user["id"],)).fetchone()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if "@" not in email or len(email) > 254:
            flash("Enter a valid email address.", "error")
        else:
            try:
                with db() as conn:
                    conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, user["id"]))
                flash("Your account information has been updated.", "success")
            except sqlite3.IntegrityError:
                flash("That email is already being used by another account.", "error")
        return redirect(url_for("account"))
    verified_at = session.get("delete_account_verified_at")
    show_delete_confirm = bool(verified_at and time.time() - verified_at <= 300)
    if verified_at and not show_delete_confirm:
        session.pop("delete_account_verified_at", None)
    return render_template(
        "account.html",
        module_id="account",
        page_title="Account",
        user=record,
        two_factor_enabled=bool(record["two_factor_secret"]),
        show_delete_confirm=show_delete_confirm,
    )


@app.route("/account/2fa", methods=["GET", "POST"])
@login_required
def account_two_factor():
    user = current_user()
    with db() as conn:
        record = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    if record["two_factor_secret"]:
        return render_template("two_factor_settings.html", module_id="account", page_title="Two-factor authentication", enabled=True)
    if request.method == "POST":
        secret = session.get("two_factor_setup_secret")
        if secret and valid_totp(secret, request.form.get("code", "").strip()):
            with db() as conn:
                conn.execute("UPDATE users SET two_factor_secret = ? WHERE id = ?", (secret, user["id"]))
            session.pop("two_factor_setup_secret", None)
            flash("Two-factor authentication is enabled.", "success")
            return redirect(url_for("account"))
        flash("That code is not valid. Try again with a new code from your app.", "error")
    secret = session.setdefault("two_factor_setup_secret", base64.b32encode(secrets.token_bytes(20)).decode().rstrip("="))
    uri = f"otpauth://totp/MarketQR:{user['email']}?secret={secret}&issuer=MarketQR"
    return render_template("two_factor_settings.html", module_id="account", page_title="Two-factor authentication", enabled=False, secret=secret, qr_image=qr_data_uri(uri))


@app.post("/account/2fa/disable")
@login_required
def disable_two_factor():
    password = request.form.get("password", "")
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (current_user()["id"],)).fetchone()
        if not check_password_hash(user["password_hash"], password):
            flash("Your password was incorrect. Two-factor authentication remains enabled.", "error")
            return redirect(url_for("account_two_factor"))
        conn.execute("UPDATE users SET two_factor_secret = NULL WHERE id = ?", (user["id"],))
    flash("Two-factor authentication has been disabled.", "success")
    return redirect(url_for("account"))


@app.post("/account/change-password")
@login_required
def change_password():
    user = current_user()
    current = request.form.get("current_password", "")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    code = request.form.get("code", "").strip()

    with db() as conn:
        stored = conn.execute(
            "SELECT password_hash, two_factor_secret FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()

    two_factor_enabled = bool(stored["two_factor_secret"])

    if not check_password_hash(stored["password_hash"], current):
        flash("Your current password is incorrect.", "error")
        return redirect(url_for("account"))

    if two_factor_enabled:
        if not code:
            flash("Enter the 6-digit code from your authenticator app.", "error")
            return redirect(url_for("account"))
        if not valid_totp(stored["two_factor_secret"], code):
            flash("That authentication code was incorrect.", "error")
            return redirect(url_for("account"))

    if len(password) < 12:
        flash("Use a password with at least 12 characters.", "error")
        return redirect(url_for("account"))
    if password != confirm:
        flash("Your new passwords do not match.", "error")
        return redirect(url_for("account"))
    if check_password_hash(stored["password_hash"], password):
        flash("Your new password must be different from your current password.", "error")
        return redirect(url_for("account"))

    with db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password, method="pbkdf2:sha256:600000"), user["id"]),
        )
    flash("Your password has been changed.", "success")
    return redirect(url_for("account"))


@app.post("/account/delete")
@login_required
def delete_account():
    user = current_user()
    password = request.form.get("password", "")
    code = request.form.get("code", "").strip()
    confirmed = request.form.get("confirmed") == "1"

    with db() as conn:
        stored = conn.execute("SELECT password_hash, two_factor_secret FROM users WHERE id = ?", (user["id"],)).fetchone()

    two_factor_enabled = bool(stored["two_factor_secret"])

    if confirmed:
        verified_at = session.pop("delete_account_verified_at", None)
        if not verified_at or time.time() - verified_at > 300:
            flash("Your deletion confirmation expired. Enter your password and try again.", "error")
            return redirect(url_for("account"))
        with db() as conn:
            conn.execute("DELETE FROM items WHERE store_id IN (SELECT id FROM stores WHERE owner_id = ?)", (user["id"],))
            conn.execute("DELETE FROM qr_codes WHERE store_id IN (SELECT id FROM stores WHERE owner_id = ?)", (user["id"],))
            conn.execute("DELETE FROM item_groups WHERE store_id IN (SELECT id FROM stores WHERE owner_id = ?)", (user["id"],))
            conn.execute("DELETE FROM store_label_assignments WHERE store_id IN (SELECT id FROM stores WHERE owner_id = ?)", (user["id"],))
            conn.execute("DELETE FROM stores WHERE owner_id = ?", (user["id"],))
            conn.execute("DELETE FROM store_labels WHERE owner_id = ?", (user["id"],))
            conn.execute("DELETE FROM store_groups WHERE owner_id = ?", (user["id"],))
            conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user["id"],))
            conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
        session.clear()
        flash("Your account and storefronts have been deleted.", "success")
        return redirect(url_for("index"))

    if not check_password_hash(stored["password_hash"], password):
        flash("Your password was incorrect. Your account was not deleted.", "error")
        return redirect(url_for("account"))

    if two_factor_enabled:
        if not code:
            flash("Enter the 6-digit code from your authenticator app.", "error")
            return redirect(url_for("account"))
        if not valid_totp(stored["two_factor_secret"], code):
            flash("That authentication code was incorrect. Your account was not deleted.", "error")
            return redirect(url_for("account"))

    session["delete_account_verified_at"] = time.time()
    return render_template(
        "account.html",
        module_id="account",
        page_title="Account",
        user={"id": user["id"], "email": user["email"]},
        two_factor_enabled=two_factor_enabled,
        show_delete_confirm=True,
    )


@app.post("/account/delete/cancel")
@login_required
def cancel_delete_account():
    session.pop("delete_account_verified_at", None)
    flash("Account deletion cancelled.", "success")
    return redirect(url_for("account"))


@app.get("/my-stores")
@login_required
def my_stores():
    return redirect(url_for("bos.store", _anchor="stores"))


@app.get("/my-stores/groups/<int:group_id>")
@login_required
def group_manage(group_id: int):
    owner_id = current_user()["id"]
    with db() as conn:
        group = conn.execute(
            "SELECT * FROM store_groups WHERE id = ? AND owner_id = ?",
            (group_id, owner_id),
        ).fetchone()
    if not group:
        abort(404)
    stats = [row for row in fetch_group_stats(owner_id) if row["id"] == group_id]
    group_stats = row_to_dict(stats[0]) if stats else row_to_dict(group)
    return render_template(
        "owner/group_manage.html",
        group=group,
        group_stats=group_stats,
        workspace=workspace_snapshot(owner_id),
        workspace_mode="group",
        focus_group_id=group_id,
    )


@app.get("/api/workspace")
@login_required
def api_workspace():
    return jsonify(workspace_snapshot(current_user()["id"]))


@app.post("/api/stores")
@login_required
def api_stores_create():
    """Create a store (JSON) — used by quick-setup wizard."""
    if not csrf_valid():
        return jsonify({"error": "Invalid CSRF token"}), 400
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Business name is required."}), 400
    owner_id = current_user()["id"]
    ws_id = session.get("active_workspace_id")
    slug = new_store_slug()
    with db() as conn:
        store_cols = {r["name"] for r in conn.execute("PRAGMA table_info(stores)").fetchall()}
        fields = ["slug", "name", "owner_id", "status"]
        values = [slug, name, owner_id, "active"]
        if "workspace_id" in store_cols and ws_id:
            fields.append("workspace_id")
            values.append(int(ws_id))
        placeholders = ", ".join("?" * len(fields))
        cur = conn.execute(
            f"INSERT INTO stores ({', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        store_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO qr_codes (store_id, name, code) VALUES (?, ?, ?)",
            (store_id, "Default", new_qr_code()),
        )
    return jsonify({"id": store_id, "slug": slug, "name": name}), 201


@app.post("/api/workspace/batch")
@login_required
def api_workspace_batch():
    if not csrf_valid():
        return jsonify({"error": "Invalid CSRF token"}), 400
    payload = request.get_json(silent=True) or {}
    action = payload.get("action", "")
    store_ids = [int(value) for value in payload.get("store_ids", []) if str(value).isdigit()]
    owner_id = current_user()["id"]
    owned_ids = owned_store_ids(owner_id, store_ids)
    if not owned_ids and action not in {"create_group", "create_label", "rename_group", "delete_group", "rename_label", "delete_label"}:
        return jsonify({"error": "Select at least one store."}), 400
    placeholders = ",".join("?" * len(owned_ids)) if owned_ids else ""
    with db() as conn:
        if action == "archive":
            conn.execute(
                f"UPDATE stores SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                owned_ids,
            )
        elif action == "activate":
            conn.execute(
                f"UPDATE stores SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                owned_ids,
            )
        elif action == "move_group":
            group_id = payload.get("group_id")
            group_value = int(group_id) if group_id not in (None, "", "null") else None
            if group_value:
                group = conn.execute(
                    "SELECT id FROM store_groups WHERE id = ? AND owner_id = ?",
                    (group_value, owner_id),
                ).fetchone()
                if not group:
                    return jsonify({"error": "Group not found."}), 404
            conn.execute(
                f"UPDATE stores SET group_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                [group_value, *owned_ids],
            )
        elif action == "add_labels":
            label_ids = [int(value) for value in payload.get("label_ids", []) if str(value).isdigit()]
            for label_id in label_ids:
                label = conn.execute(
                    "SELECT id FROM store_labels WHERE id = ? AND owner_id = ?",
                    (label_id, owner_id),
                ).fetchone()
                if not label:
                    continue
                for store_id in owned_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO store_label_assignments (store_id, label_id) VALUES (?, ?)",
                        (store_id, label_id),
                    )
        elif action == "remove_labels":
            label_ids = [int(value) for value in payload.get("label_ids", []) if str(value).isdigit()]
            for label_id in label_ids:
                conn.execute(
                    f"DELETE FROM store_label_assignments WHERE label_id = ? AND store_id IN ({placeholders})",
                    [label_id, *owned_ids],
                )
        elif action == "duplicate":
            for store_id in owned_ids:
                duplicate_store_record(conn, store_id, owner_id)
        elif action == "export":
            stores = fetch_workspace_stores(owner_id)
            exported = [store for store in stores if store["id"] in owned_ids]
            return jsonify({"stores": exported, "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        elif action == "delete":
            for store_id in owned_ids:
                conn.execute("DELETE FROM items WHERE store_id = ?", (store_id,))
                conn.execute("DELETE FROM qr_codes WHERE store_id = ?", (store_id,))
                conn.execute("DELETE FROM item_groups WHERE store_id = ?", (store_id,))
                conn.execute("DELETE FROM store_label_assignments WHERE store_id = ?", (store_id,))
            conn.execute(f"DELETE FROM stores WHERE id IN ({placeholders})", owned_ids)
        elif action == "rename":
            store_id = owned_ids[0] if owned_ids else None
            name = (payload.get("name") or "").strip()
            if store_id and name:
                conn.execute(
                    "UPDATE stores SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (name, store_id),
                )
            else:
                return jsonify({"error": "Name is required."}), 400
        elif action == "create_group":
            name = (payload.get("name") or "").strip()
            if not name:
                return jsonify({"error": "Group name is required."}), 400
            cursor = conn.execute(
                "INSERT INTO store_groups (owner_id, name) VALUES (?, ?)",
                (owner_id, name),
            )
            new_group_id = cursor.lastrowid
            if owned_ids:
                conn.execute(
                    f"UPDATE stores SET group_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                    [new_group_id, *owned_ids],
                )
        elif action == "create_label":
            name = (payload.get("name") or "").strip()
            if not name:
                return jsonify({"error": "Label name is required."}), 400
            cursor = conn.execute(
                "INSERT INTO store_labels (owner_id, name) VALUES (?, ?)",
                (owner_id, name),
            )
            label_id = cursor.lastrowid
            for store_id in owned_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO store_label_assignments (store_id, label_id) VALUES (?, ?)",
                    (store_id, label_id),
                )
        elif action == "rename_group":
            group_id = payload.get("group_id")
            name = (payload.get("name") or "").strip()
            if group_id and name:
                conn.execute(
                    "UPDATE store_groups SET name = ? WHERE id = ? AND owner_id = ?",
                    (name, int(group_id), owner_id),
                )
            else:
                return jsonify({"error": "Group name is required."}), 400
        elif action == "delete_group":
            group_id = payload.get("group_id")
            if group_id:
                conn.execute(
                    "UPDATE stores SET group_id = NULL WHERE group_id = ? AND owner_id = ?",
                    (int(group_id), owner_id),
                )
                conn.execute(
                    "DELETE FROM store_groups WHERE id = ? AND owner_id = ?",
                    (int(group_id), owner_id),
                )
        elif action == "rename_label":
            label_id = payload.get("label_id")
            name = (payload.get("name") or "").strip()
            if label_id and name:
                conn.execute(
                    "UPDATE store_labels SET name = ? WHERE id = ? AND owner_id = ?",
                    (name, int(label_id), owner_id),
                )
            else:
                return jsonify({"error": "Label name is required."}), 400
        elif action == "delete_label":
            label_id = payload.get("label_id")
            if label_id:
                conn.execute("DELETE FROM store_label_assignments WHERE label_id = ?", (int(label_id),))
                conn.execute(
                    "DELETE FROM store_labels WHERE id = ? AND owner_id = ?",
                    (int(label_id), owner_id),
                )
        else:
            return jsonify({"error": "Unknown action."}), 400
    return jsonify(workspace_snapshot(owner_id))


@app.post("/my-stores/batch")
@login_required
def batch_stores():
    flash("Use the workspace action bar for batch operations.", "success")
    return redirect(url_for("my_stores"))


@app.route("/my-stores/groups", methods=["GET", "POST"])
@login_required
def store_groups_manage():
    flash("Group changes are handled in the store workspace.", "success")
    return redirect(url_for("my_stores"))


@app.route("/create", methods=["GET", "POST"])
@login_required
def create_store():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Your business name is required.", "error")
            return render_template("create_store.html")
        slug = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8].lower()
        with db() as conn:
            cursor = conn.execute(
                "INSERT INTO stores (slug, name, owner_name, contact, description, owner_id, address, business_hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    slug,
                    name,
                    request.form.get("owner_name", "").strip(),
                    request.form.get("contact", "").strip(),
                    request.form.get("description", "").strip(),
                    current_user()["id"],
                    request.form.get("address", "").strip(),
                    request.form.get("business_hours", "").strip(),
                ),
            )
            store_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO qr_codes (store_id, name, code) VALUES (?, ?, ?)",
                (store_id, "Default", new_qr_code()),
            )
        return redirect(url_for("manage_store", slug=slug))
    return render_template("create_store.html")


@app.route("/manage/<slug>", methods=["GET", "POST"])
@login_required
def manage_store(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    group_filter = request.args.get("group")
    active_group, group_nav, show_group_nav, active_group_name = resolve_item_group_context(store["id"], group_filter, published_only=False)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        if not name or not price:
            flash("Item name and price are required.", "error")
        else:
            try:
                value = float(price)
                if value < 0:
                    raise ValueError
                image_url = resolve_image_field("image_url", "image_file")
                with db() as conn:
                    conn.execute(
                        """INSERT INTO items (store_id, name, price, description, image_url, group_id, sku, inventory, status, display_order)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT MAX(display_order) + 1 FROM items WHERE store_id = ?), 0))""",
                        (
                            store["id"],
                            name,
                            value,
                            request.form.get("description", "").strip(),
                            image_url,
                            request.form.get("group_id") or None,
                            request.form.get("sku", "").strip() or None,
                            request.form.get("inventory", type=int),
                            request.form.get("status", "published"),
                            store["id"],
                        ),
                    )
                flash("Item added to your storefront.", "success")
                redirect_group = group_query_param(active_group) if show_group_nav and active_group else None
                return redirect(url_for("manage_store", slug=slug, group=redirect_group) if redirect_group else url_for("manage_store", slug=slug))
            except ValueError as exc:
                message = str(exc)
                if message.startswith("Use a JPG"):
                    flash(message, "error")
                else:
                    flash("Use a valid non-negative price.", "error")
    items = owner_items(store["id"], active_group)
    qr_codes = store_qr_codes(store["id"])
    primary_qr = qr_codes[0] if qr_codes else None
    primary_qr_image = qr_data_uri(public_url_for("qr_entry", code=primary_qr["code"])) if primary_qr else None
    return render_template(
        "owner/manage.html",
        store=store,
        items=items,
        group_nav=group_nav,
        show_group_nav=show_group_nav,
        active_group=active_group,
        active_group_name=active_group_name,
        item_groups=store_item_groups(store["id"]),
        qr_codes=qr_codes,
        primary_qr=primary_qr,
        primary_qr_image=primary_qr_image,
    )


@app.route("/manage/<slug>/settings", methods=["GET", "POST"])
@login_required
def store_settings(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "delete":
            with db() as conn:
                conn.execute("DELETE FROM items WHERE store_id = ?", (store["id"],))
                conn.execute("DELETE FROM qr_codes WHERE store_id = ?", (store["id"],))
                conn.execute("DELETE FROM item_groups WHERE store_id = ?", (store["id"],))
                conn.execute("DELETE FROM stores WHERE id = ?", (store["id"],))
            flash(f'"{store["name"]}" and all associated items and QR codes were permanently deleted.', "success")
            return redirect(url_for("my_stores"))
        try:
            background_image = resolve_image_field("background_image", "background_file", store["background_image"])
            logo_url = resolve_image_field("logo_url", "logo_file", store["logo_url"] if "logo_url" in store.keys() else None)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("store_settings", slug=slug))
        from storefront_platform import hours_from_form, DEFAULT_TIMEZONE

        hours_json = hours_from_form(request.form)
        timezone = request.form.get("timezone", "").strip() or DEFAULT_TIMEZONE
        new_address = request.form.get("address", "").strip()
        with db() as conn:
            conn.execute(
                """UPDATE stores SET name = ?, description = ?, owner_name = ?, contact = ?, address = ?,
                   business_hours_json = ?, timezone = ?, logo_url = ?, background_image = ?, group_id = ?,
                   updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (
                    request.form.get("name", "").strip() or store["name"],
                    request.form.get("description", "").strip(),
                    request.form.get("owner_name", "").strip(),
                    request.form.get("contact", "").strip(),
                    new_address,
                    hours_json,
                    timezone,
                    logo_url,
                    background_image,
                    request.form.get("group_id") or None,
                    store["id"],
                ),
            )
            from storefront_platform import sync_store_geocode

            if new_address != (store["address"] or ""):
                sync_store_geocode(conn, store["id"], new_address)
        flash("Store settings saved.", "success")
        return redirect(url_for("store_settings", slug=slug))
    from storefront_platform import parse_hours_json, WEEKDAYS, WEEKDAY_LABELS, DEFAULT_TIMEZONE

    hours_data = parse_hours_json(store["business_hours_json"] if "business_hours_json" in store.keys() else None)
    return render_template(
        "owner/store_settings.html",
        store=store,
        store_groups=owner_store_groups(current_user()["id"]),
        hours_data=hours_data,
        weekdays=WEEKDAYS,
        weekday_labels=WEEKDAY_LABELS,
        default_timezone=DEFAULT_TIMEZONE,
    )


@app.route("/manage/<slug>/deals", methods=["GET", "POST"])
@login_required
def manage_store_deals(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    from storefront_platform import list_store_deals, save_deal_from_form, resolve_deal, deal_schedule_status

    items = owner_items(store["id"])
    if request.method == "POST":
        with db() as conn:
            for item in items:
                save_deal_from_form(conn, store["id"], item["id"], request.form)
        flash("Deals saved.", "success")
        return redirect(url_for("manage_store_deals", slug=slug))

    with db() as conn:
        deal_rows = {r["item_id"]: r for r in list_store_deals(conn, store["id"])}
    deals_by_item = {}
    deal_status_by_item = {}
    for item in items:
        row = deal_rows.get(item["id"])
        if row:
            deals_by_item[item["id"]] = resolve_deal(row, float(item["price"]))
            deal_status_by_item[item["id"]] = deal_schedule_status(row)
    return render_template(
        "owner/store_deals.html",
        store=store,
        items=items,
        deals_by_item=deals_by_item,
        deal_rows=deal_rows,
        deal_status_by_item=deal_status_by_item,
    )


@app.get("/manage/<slug>/preview")
@login_required
def store_preview(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    ctx = storefront_render_context(
        store,
        preview_mode=True,
        group_filter=request.args.get("group"),
        view=request.args.get("view", "shop"),
        group_in_url="group" in request.args,
    )
    return render_template("customer/storefront.html", **ctx)


@app.route("/manage/<slug>/qr-codes", methods=["GET", "POST"])
@login_required
def manage_qr_codes(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            name = request.form.get("name", "").strip() or "Untitled QR"
            code = new_qr_code()
            with db() as conn:
                conn.execute("INSERT INTO qr_codes (store_id, name, code) VALUES (?, ?, ?)", (store["id"], name, code))
            flash("QR code created.", "success")
        elif action == "delete":
            qr_id = request.form.get("qr_id", type=int)
            with db() as conn:
                count = conn.execute("SELECT COUNT(*) AS total FROM qr_codes WHERE store_id = ?", (store["id"],)).fetchone()["total"]
                if count <= 1:
                    flash("Each store must keep at least one QR code.", "error")
                else:
                    conn.execute("DELETE FROM qr_codes WHERE id = ? AND store_id = ?", (qr_id, store["id"]))
                    flash("QR code deleted.", "success")
    qr_codes = store_qr_codes(store["id"])
    qr_payload = [
        {
            "record": qr,
            "url": public_url_for("qr_entry", code=qr["code"]),
            "image": qr_data_uri(public_url_for("qr_entry", code=qr["code"])),
        }
        for qr in qr_codes
    ]
    return render_template("owner/qr_codes.html", store=store, qr_codes=qr_payload)


@app.get("/manage/<slug>/preview/qr/<code>")
@login_required
def qr_preview(slug: str, code: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    with db() as conn:
        qr = conn.execute("SELECT * FROM qr_codes WHERE store_id = ? AND code = ?", (store["id"], code)).fetchone()
    if not qr:
        abort(404)
    active_group, group_nav, show_group_nav, active_group_name = resolve_item_group_context(store["id"], None, published_only=True)
    ctx = storefront_render_context(store, preview_mode=True)
    ctx["items"] = customer_items(store["id"], active_group)
    ctx["group_nav"] = group_nav
    ctx["show_group_nav"] = show_group_nav
    ctx["active_group"] = active_group
    ctx["active_group_name"] = active_group_name
    ctx["qr_label"] = qr["name"]
    return render_template("customer/storefront.html", **ctx)


@app.route("/manage/<slug>/groups", methods=["GET", "POST"])
@login_required
def item_groups_manage(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            name = request.form.get("name", "").strip()
            if name:
                with db() as conn:
                    conn.execute(
                        "INSERT INTO item_groups (store_id, name, display_order) VALUES (?, ?, COALESCE((SELECT MAX(display_order) + 1 FROM item_groups WHERE store_id = ?), 0))",
                        (store["id"], name, store["id"]),
                    )
                flash("Item group created.", "success")
        elif action == "rename":
            group_id = request.form.get("group_id", type=int)
            name = request.form.get("name", "").strip()
            if group_id and name:
                with db() as conn:
                    conn.execute("UPDATE item_groups SET name = ? WHERE id = ? AND store_id = ?", (name, group_id, store["id"]))
                flash("Item group renamed.", "success")
        elif action == "delete":
            group_id = request.form.get("group_id", type=int)
            if group_id:
                with db() as conn:
                    conn.execute("UPDATE items SET group_id = NULL WHERE group_id = ? AND store_id = ?", (group_id, store["id"]))
                    conn.execute("DELETE FROM item_groups WHERE id = ? AND store_id = ?", (group_id, store["id"]))
                flash("Item group deleted.", "success")
        elif action == "reorder":
            order = request.form.get("order", "")
            ids = [int(value) for value in order.split(",") if value.isdigit()]
            with db() as conn:
                for index, group_id in enumerate(ids):
                    conn.execute(
                        "UPDATE item_groups SET display_order = ? WHERE id = ? AND store_id = ?",
                        (index, group_id, store["id"]),
                    )
            flash("Item group order updated.", "success")
            return redirect(url_for("item_groups_manage", slug=slug))
        elif action == "move_item":
            item_id = request.form.get("item_id", type=int)
            group_id = request.form.get("group_id")
            group_value = int(group_id) if group_id else None
            if item_id:
                with db() as conn:
                    conn.execute(
                        "UPDATE items SET group_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?",
                        (group_value, item_id, store["id"]),
                    )
                flash("Item moved to the selected group.", "success")
    groups = store_item_groups(store["id"])
    items = owner_items(store["id"])
    group_counts = {}
    for item in items:
        if item["group_id"]:
            group_counts[item["group_id"]] = group_counts.get(item["group_id"], 0) + 1
    return render_template("owner/item_groups.html", store=store, item_groups=groups, items=items, group_counts=group_counts)


@app.get("/manage/<slug>/items/<int:item_id>")
@login_required
def owner_item_detail(slug: str, item_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    item = get_item_or_404(store["id"], item_id)
    with db() as conn:
        group_name = None
        if item["group_id"]:
            group_name = conn.execute("SELECT name FROM item_groups WHERE id = ?", (item["group_id"],)).fetchone()
    return render_template(
        "owner/item_detail.html",
        store=store,
        item=item,
        group_name=group_name["name"] if group_name else None,
        qr_codes=store_qr_codes(store["id"]),
    )


@app.route("/manage/<slug>/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(slug: str, item_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    item = get_item_or_404(store["id"], item_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        if not name or not price:
            flash("Item name and price are required.", "error")
        else:
            try:
                value = float(price)
                if value < 0:
                    raise ValueError
                try:
                    image_url = resolve_image_field("image_url", "image_file", item["image_url"])
                except ValueError as exc:
                    flash(str(exc), "error")
                    return redirect(url_for("edit_item", slug=slug, item_id=item_id))
                with db() as conn:
                    conn.execute(
                        """UPDATE items SET name = ?, price = ?, description = ?, image_url = ?, group_id = ?,
                           sku = ?, inventory = ?, status = ?, internal_notes = ?, display_order = ?,
                           updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?""",
                        (
                            name,
                            value,
                            request.form.get("description", "").strip(),
                            image_url,
                            request.form.get("group_id") or None,
                            request.form.get("sku", "").strip() or None,
                            request.form.get("inventory", type=int),
                            request.form.get("status", "published"),
                            request.form.get("internal_notes", "").strip(),
                            request.form.get("display_order", type=int) or 0,
                            item_id,
                            store["id"],
                        ),
                    )
                flash("Item updated.", "success")
                return redirect(url_for("owner_item_detail", slug=slug, item_id=item_id))
            except ValueError:
                flash("Use a valid non-negative price.", "error")
    return render_template(
        "owner/item_edit.html",
        store=store,
        item=item,
        item_groups=store_item_groups(store["id"]),
    )


@app.get("/manage/<slug>/items/<int:item_id>/preview")
@login_required
def item_preview(slug: str, item_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    item = get_item_or_404(store["id"], item_id)
    if item["status"] != "published":
        flash("This item is not published. Preview shows the customer view anyway.", "success")
    with db() as conn:
        group_name = None
        if item["group_id"]:
            row = conn.execute("SELECT name FROM item_groups WHERE id = ?", (item["group_id"],)).fetchone()
            group_name = row["name"] if row else None
    back_group = parse_item_group_arg(request.args.get("group"))
    preview_item = dict(item)
    deal = None
    with db() as conn:
        from storefront_platform import deals_map_for_items
        deal = deals_map_for_items(conn, store["id"]).get(item_id)
    return render_template(
        "customer/item_detail.html",
        store=store,
        item=preview_item,
        deal=deal,
        group_name=group_name,
        preview_mode=True,
        back_group=group_query_param(back_group) if back_group else None,
    )


@app.post("/manage/<slug>/items/<int:item_id>/delete")
@login_required
def delete_item(slug: str, item_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    with db() as conn:
        conn.execute("DELETE FROM items WHERE id = ? AND store_id = ?", (item_id, store["id"]))
    flash("Item permanently deleted.", "success")
    return redirect(url_for("manage_store", slug=slug))


@app.post("/manage/<slug>/items/reorder")
@login_required
def reorder_items(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    order = request.form.get("order", "")
    ids = [int(value) for value in order.split(",") if value.isdigit()]
    with db() as conn:
        for index, item_id in enumerate(ids):
            conn.execute(
                "UPDATE items SET display_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?",
                (index, item_id, store["id"]),
            )
    flash("Item order updated.", "success")
    return redirect(url_for("manage_store", slug=slug))


@app.get("/qr/<code>")
def qr_entry(code: str):
    code = code.lower()
    attendee = attendee_by_code(code)
    if attendee:
        return redirect(url_for("event_pass_view", code=code))
    card = business_card_by_code(code)
    if card and card["status"] != "archived":
        return redirect(url_for("business_card_view", code=code))
    product = qr_product_by_code(code)
    if product and product["status"] != "archived":
        return redirect(url_for("product_info_view", code=code))
    point = check_in_point_by_code(code)
    if point and point["status"] != "archived":
        return redirect(url_for("check_in_view", code=code))
    feedback_form = getattr(app, "feedback_form_by_code", None)
    if feedback_form:
        form = feedback_form(code)
        if form and form["status"] not in ("archived", "draft"):
            return redirect(url_for("feedback_submit_view", code=code))
    with db() as conn:
        qr = conn.execute(
            "SELECT qr_codes.*, stores.slug, stores.status FROM qr_codes JOIN stores ON qr_codes.store_id = stores.id WHERE qr_codes.code = ?",
            (code,),
        ).fetchone()
    qr_status = qr["status"] if "status" in qr.keys() and qr["status"] else "active"
    if not qr or qr_status == "archived":
        abort(404)
    # Track QR Experience scan — runtime handles session on /e/ landing
    if "experience_id" in qr.keys() and qr["experience_id"]:
        try:
            with db() as conn:
                exp = conn.execute(
                    "SELECT id, workspace_id, status, public_slug FROM qr_experiences WHERE id=?",
                    (qr["experience_id"],),
                ).fetchone()
                if exp and exp["status"] == "active":
                    slug = exp["public_slug"] if exp["public_slug"] else code
                    return redirect(f"/e/{slug}?from=qr")
        except Exception:
            pass
    pass_type = (qr["pass_type"] if qr["pass_type"] else "storefront") if "pass_type" in qr.keys() else "storefront"
    if pass_type == "experience":
        with db() as conn:
            exp = conn.execute(
                "SELECT public_slug FROM qr_experiences WHERE qr_code_id=?", (qr["id"],)
            ).fetchone()
            slug = (exp["public_slug"] if exp and exp["public_slug"] else code)
        return redirect(f"/e/{slug}?from=qr")
    ref_id = qr["ref_id"] if "ref_id" in qr.keys() else None
    if pass_type == "event_pass" and ref_id:
        return redirect(url_for("event_pass_preview", slug=qr["slug"], event_id=ref_id))
    if pass_type == "business_card" and ref_id:
        card = get_business_card_or_404(qr["store_id"], ref_id)
        return redirect(url_for("business_card_view", code=card["card_code"]))
    if pass_type == "product_info" and ref_id:
        product = get_qr_product_or_404(qr["store_id"], ref_id)
        return redirect(url_for("product_info_view", code=product["product_code"]))
    if pass_type == "check_in" and ref_id:
        point = get_check_in_point_or_404(qr["store_id"], ref_id)
        return redirect(url_for("check_in_view", code=point["point_code"]))
    if pass_type == "feedback" and ref_id:
        with db() as conn:
            pub = conn.execute(
                "SELECT pub_code FROM feedback_publications WHERE template_id = ? AND store_id = ? LIMIT 1",
                (ref_id, qr["store_id"]),
            ).fetchone()
        if pub:
            return redirect(url_for("feedback_submit_view", code=pub["pub_code"]))
    if pass_type == "survey" and ref_id:
        with db() as conn:
            survey = conn.execute(
                "SELECT pub_code FROM surveys WHERE id=? AND status='published'", (ref_id,)
            ).fetchone()
        if survey and survey["pub_code"]:
            return redirect(url_for("survey_submit_view", code=survey["pub_code"]))
    if pass_type == "booking":
        # Booking experiences land on the storefront until a dedicated booking page exists
        return redirect(url_for("storefront", slug=qr["slug"], qr=code))
    return redirect(url_for("storefront", slug=qr["slug"], qr=code))


@app.get("/pass/<code>")
def event_pass_view(code: str):
    attendee = attendee_by_code(code)
    if not attendee:
        abort(404)
    if attendee["event_status"] == "draft":
        abort(404)
    qr = attendee_qr_payload(attendee)
    return render_template(
        "customer/event_pass.html",
        attendee=attendee,
        pass_url=qr["url"],
        pass_image=qr["image"],
        preview_mode=False,
    )


@app.get("/manage/<slug>/preview/pass/<code>")
@login_required
def event_pass_owner_preview(slug: str, code: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    attendee = attendee_by_code(code)
    if not attendee or attendee["store_slug"] != slug:
        abort(404)
    qr = attendee_qr_payload(attendee)
    return render_template(
        "customer/event_pass.html",
        attendee=attendee,
        pass_url=qr["url"],
        pass_image=qr["image"],
        preview_mode=True,
    )


@app.route("/manage/<slug>/event-passes", methods=["GET", "POST"])
@login_required
def manage_event_passes(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            with db() as conn:
                conn.execute(
                    """INSERT INTO events (store_id, name, description, event_date, start_time, end_time,
                       timezone, venue, capacity, status, internal_notes, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (
                        store["id"],
                        request.form.get("name", "").strip() or "Untitled Event",
                        request.form.get("description", "").strip(),
                        request.form.get("event_date", "").strip(),
                        request.form.get("start_time", "").strip(),
                        request.form.get("end_time", "").strip(),
                        request.form.get("timezone", "Asia/Singapore").strip(),
                        request.form.get("venue", "").strip(),
                        request.form.get("capacity", type=int) or 100,
                        request.form.get("status", "draft"),
                        request.form.get("internal_notes", "").strip(),
                    ),
                )
            flash("Event created.", "success")
        elif action == "duplicate":
            event_id = request.form.get("event_id", type=int)
            event = get_event_or_404(store["id"], event_id)
            with db() as conn:
                cur = conn.execute(
                    """INSERT INTO events (store_id, name, description, event_date, start_time, end_time,
                       timezone, venue, capacity, status, internal_notes, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, CURRENT_TIMESTAMP)""",
                    (
                        store["id"],
                        f"{event['name']} (copy)",
                        event["description"],
                        event["event_date"],
                        event["start_time"],
                        event["end_time"],
                        event["timezone"],
                        event["venue"],
                        event["capacity"],
                        event["internal_notes"],
                    ),
                )
                new_id = cur.lastrowid
                for att in event_attendees(event_id):
                    conn.execute(
                        "INSERT INTO event_attendees (event_id, name, email, pass_code) VALUES (?, ?, ?, ?)",
                        (new_id, att["name"], att["email"], unique_pass_code(conn)),
                    )
            flash("Event duplicated.", "success")
        elif action == "archive":
            event_id = request.form.get("event_id", type=int)
            with db() as conn:
                conn.execute(
                    "UPDATE events SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?",
                    (event_id, store["id"]),
                )
            flash("Event archived.", "success")
        elif action == "delete":
            event_id = request.form.get("event_id", type=int)
            with db() as conn:
                conn.execute("DELETE FROM events WHERE id = ? AND store_id = ?", (event_id, store["id"]))
            flash("Event deleted.", "success")
    events = store_events(store["id"])
    event_rows = []
    for event in events:
        stats = event_stats(event["id"])
        event_rows.append({"event": event, "stats": stats})
    return render_template("owner/event_passes.html", store=store, event_rows=event_rows, event_statuses=EVENT_STATUSES)


@app.route("/manage/<slug>/event-passes/<int:event_id>", methods=["GET", "POST"])
@login_required
def manage_event_pass_detail(slug: str, event_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    event = get_event_or_404(store["id"], event_id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update":
            with db() as conn:
                conn.execute(
                    """UPDATE events SET name = ?, cover_image = ?, description = ?, event_date = ?,
                       start_time = ?, end_time = ?, timezone = ?, venue = ?, capacity = ?,
                       status = ?, internal_notes = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ? AND store_id = ?""",
                    (
                        request.form.get("name", "").strip() or event["name"],
                        resolve_image_field("cover_image", "cover_file", event["cover_image"]),
                        request.form.get("description", "").strip(),
                        request.form.get("event_date", "").strip(),
                        request.form.get("start_time", "").strip(),
                        request.form.get("end_time", "").strip(),
                        request.form.get("timezone", "Asia/Singapore").strip(),
                        request.form.get("venue", "").strip(),
                        request.form.get("capacity", type=int) or event["capacity"],
                        request.form.get("status", event["status"]),
                        request.form.get("internal_notes", "").strip(),
                        event_id,
                        store["id"],
                    ),
                )
            flash("Event updated.", "success")
            return redirect(url_for("manage_event_pass_detail", slug=slug, event_id=event_id))
        if action == "add_attendee":
            name = request.form.get("name", "").strip()
            if name:
                with db() as conn:
                    cur = conn.execute(
                        "INSERT INTO event_attendees (event_id, name, email, pass_code) VALUES (?, ?, ?, ?)",
                        (event_id, name, request.form.get("email", "").strip(), unique_pass_code(conn)),
                    )
                    link_event_attendee_customer(
                        conn, event_id, cur.lastrowid, name, request.form.get("email", "").strip(),
                    )
                flash("Attendee added.", "success")
        elif action == "bulk_generate":
            count = min(max(request.form.get("count", type=int) or 1, 1), 500)
            prefix = request.form.get("name_prefix", "Guest").strip() or "Guest"
            with db() as conn:
                existing = conn.execute(
                    "SELECT COUNT(*) AS c FROM event_attendees WHERE event_id = ?", (event_id,)
                ).fetchone()["c"]
                for i in range(count):
                    n = existing + i + 1
                    conn.execute(
                        "INSERT INTO event_attendees (event_id, name, email, pass_code) VALUES (?, ?, ?, ?)",
                        (event_id, f"{prefix} {n}", "", unique_pass_code(conn)),
                    )
            flash(f"Generated {count} passes.", "success")
        elif action == "remove_attendees":
            ids = [int(x) for x in request.form.getlist("attendee_ids") if x.isdigit()]
            if ids:
                with db() as conn:
                    conn.executemany(
                        "DELETE FROM event_attendees WHERE id = ? AND event_id = ?",
                        [(aid, event_id) for aid in ids],
                    )
                flash(f"Removed {len(ids)} attendee(s).", "success")
        elif action == "export":
            pass  # handled via GET export route
    attendees = event_attendees(event_id)
    stats = event_stats(event_id)
    attendee_payload = []
    for att in attendees:
        qr = attendee_qr_payload(att)
        attendee_payload.append({"record": att, "url": qr["url"], "image": qr["image"]})
    scan_log = []
    with db() as conn:
        rows = conn.execute(
            """SELECT psl.*, ea.name AS attendee_name
               FROM pass_scan_log psl
               JOIN event_attendees ea ON ea.id = psl.attendee_id
               WHERE ea.event_id = ?
               ORDER BY psl.scanned_at DESC LIMIT 50""",
            (event_id,),
        ).fetchall()
        scan_log = rows
    return render_template(
        "owner/event_pass_detail.html",
        store=store,
        event=event,
        stats=stats,
        attendees=attendee_payload,
        scan_log=scan_log,
        event_statuses=EVENT_STATUSES,
    )


@app.get("/manage/<slug>/event-passes/<int:event_id>/export")
@login_required
def export_event_attendees(slug: str, event_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    get_event_or_404(store["id"], event_id)
    attendees = event_attendees(event_id)
    lines = ["name,email,pass_code,pass_status,checked_in_at,pass_url"]
    for att in attendees:
        url = public_url_for("event_pass_view", code=att["pass_code"])
        lines.append(
            f'"{att["name"]}","{att["email"] or ""}","{att["pass_code"]}","{att["pass_status"]}","{att["checked_in_at"] or ""}","{url}"'
        )
    from flask import Response
    return Response(
        "\n".join(lines),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=event-{event_id}-attendees.csv"},
    )


@app.get("/manage/<slug>/event-passes/<int:event_id>/scanner")
@login_required
def event_pass_scanner(slug: str, event_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    event = get_event_or_404(store["id"], event_id)
    stats = event_stats(event_id)
    return render_template(
        "owner/event_pass_scanner.html",
        store=store,
        event=event,
        stats=stats,
    )


@app.get("/manage/<slug>/preview/event/<int:event_id>")
@login_required
def event_pass_preview(slug: str, event_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    event = get_event_or_404(store["id"], event_id)
    attendees = event_attendees(event_id)
    sample = attendees[0] if attendees else None
    if not sample:
        flash("Add at least one attendee to preview a pass.", "error")
        return redirect(url_for("manage_event_pass_detail", slug=slug, event_id=event_id))
    return redirect(url_for("event_pass_owner_preview", slug=slug, code=sample["pass_code"]))


# --- Business Cards ---

@app.get("/card/<code>")
def business_card_view(code: str):
    card = business_card_by_code(code)
    if not card or card["status"] == "archived":
        abort(404)
    if card["status"] == "draft":
        abort(404)
    increment_scan_count("business_cards", card["id"])
    social = parse_social_links(card["social_links"])
    qr = entity_qr_payload("business_card_view", card["card_code"])
    return render_template(
        "customer/business_card.html",
        card=card,
        social=social,
        qr_url=qr["url"],
        qr_image=qr["image"],
        preview_mode=False,
    )


@app.get("/card/<code>/contact.vcf")
def business_card_vcard(code: str):
    card = business_card_by_code(code)
    if not card or card["status"] not in ("published",):
        abort(404)
    content = build_vcard(card)
    return app.response_class(content, mimetype="text/vcard", headers={
        "Content-Disposition": f'attachment; filename="{card["name"].replace(" ", "_")}.vcf"',
    })


@app.get("/manage/<slug>/preview/card/<code>")
@login_required
def business_card_owner_preview(slug: str, code: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    card = business_card_by_code(code)
    if not card or card["store_slug"] != slug:
        abort(404)
    social = parse_social_links(card["social_links"])
    qr = entity_qr_payload("business_card_view", card["card_code"])
    return render_template(
        "customer/business_card.html",
        card=card,
        social=social,
        qr_url=qr["url"],
        qr_image=qr["image"],
        preview_mode=True,
    )


@app.route("/manage/<slug>/business-cards", methods=["GET", "POST"])
@login_required
def manage_business_cards(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            with db() as conn:
                code = unique_entity_code(conn, "business_cards", "card_code")
                conn.execute(
                    """INSERT INTO business_cards (store_id, card_code, name, status, updated_at)
                       VALUES (?, ?, ?, 'draft', CURRENT_TIMESTAMP)""",
                    (store["id"], code, request.form.get("name", "").strip() or "Untitled Card"),
                )
            flash("Business card created.", "success")
        elif action == "duplicate":
            card_id = request.form.get("card_id", type=int)
            card = get_business_card_or_404(store["id"], card_id)
            with db() as conn:
                code = unique_entity_code(conn, "business_cards", "card_code")
                conn.execute(
                    """INSERT INTO business_cards (store_id, card_code, profile_photo, name, position, company,
                       phone, email, website, address, social_links, biography, company_logo, group_name, status, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', CURRENT_TIMESTAMP)""",
                    (
                        store["id"], code, card["profile_photo"], f"{card['name']} (copy)",
                        card["position"], card["company"], card["phone"], card["email"],
                        card["website"], card["address"], card["social_links"], card["biography"],
                        card["company_logo"], card["group_name"],
                    ),
                )
            flash("Business card duplicated.", "success")
        elif action == "archive":
            card_id = request.form.get("card_id", type=int)
            with db() as conn:
                conn.execute(
                    "UPDATE business_cards SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?",
                    (card_id, store["id"]),
                )
            flash("Business card archived.", "success")
        elif action == "delete":
            card_id = request.form.get("card_id", type=int)
            with db() as conn:
                conn.execute("DELETE FROM business_cards WHERE id = ? AND store_id = ?", (card_id, store["id"]))
            flash("Business card deleted.", "success")
    cards = store_business_cards(store["id"])
    groups = sorted({c["group_name"] for c in cards if c["group_name"]})
    return render_template(
        "owner/business_cards.html",
        store=store,
        cards=cards,
        groups=groups,
        entity_statuses=QR_ENTITY_STATUSES,
    )


@app.route("/manage/<slug>/business-cards/<int:card_id>", methods=["GET", "POST"])
@login_required
def manage_business_card_detail(slug: str, card_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    card = get_business_card_or_404(store["id"], card_id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update":
            with db() as conn:
                conn.execute(
                    """UPDATE business_cards SET profile_photo = ?, name = ?, position = ?, company = ?,
                       phone = ?, email = ?, website = ?, address = ?, social_links = ?, biography = ?,
                       company_logo = ?, group_name = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ? AND store_id = ?""",
                    (
                        resolve_image_field("profile_photo", "profile_file", card["profile_photo"]),
                        request.form.get("name", "").strip() or card["name"],
                        request.form.get("position", "").strip(),
                        request.form.get("company", "").strip(),
                        request.form.get("phone", "").strip(),
                        request.form.get("email", "").strip(),
                        request.form.get("website", "").strip(),
                        request.form.get("address", "").strip(),
                        social_links_from_form() or card["social_links"],
                        request.form.get("biography", "").strip(),
                        resolve_image_field("company_logo", "logo_file", card["company_logo"]),
                        request.form.get("group_name", "").strip(),
                        request.form.get("status", card["status"]),
                        card_id, store["id"],
                    ),
                )
            flash("Business card updated.", "success")
        elif action == "regenerate":
            with db() as conn:
                regenerate_entity_code(conn, "business_cards", card_id, store["id"])
            flash("QR code regenerated.", "success")
        return redirect(url_for("manage_business_card_detail", slug=slug, card_id=card_id))
    card = get_business_card_or_404(store["id"], card_id)
    qr = entity_qr_payload("business_card_view", card["card_code"])
    social = parse_social_links(card["social_links"])
    return render_template(
        "owner/business_card_detail.html",
        store=store,
        card=card,
        qr=qr,
        social=social,
        entity_statuses=QR_ENTITY_STATUSES,
    )


# --- Product Information QR ---

@app.get("/product/<code>")
def product_info_view(code: str):
    product = qr_product_by_code(code)
    if not product or product["status"] == "archived":
        abort(404)
    if product["status"] == "draft":
        abort(404)
    increment_scan_count("qr_products", product["id"])
    related = related_qr_products(product["store_id"], product["category"], product["id"])
    qr = entity_qr_payload("product_info_view", product["product_code"])
    return render_template(
        "customer/product_info.html",
        product=product,
        related=related,
        qr_url=qr["url"],
        qr_image=qr["image"],
        preview_mode=False,
    )


@app.get("/manage/<slug>/preview/product/<code>")
@login_required
def product_info_owner_preview(slug: str, code: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    product = qr_product_by_code(code)
    if not product or product["store_slug"] != slug:
        abort(404)
    related = related_qr_products(product["store_id"], product["category"], product["id"])
    qr = entity_qr_payload("product_info_view", product["product_code"])
    return render_template(
        "customer/product_info.html",
        product=product,
        related=related,
        qr_url=qr["url"],
        qr_image=qr["image"],
        preview_mode=True,
    )


@app.route("/manage/<slug>/product-qr", methods=["GET", "POST"])
@login_required
def manage_product_qr(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            with db() as conn:
                code = unique_entity_code(conn, "qr_products", "product_code")
                conn.execute(
                    """INSERT INTO qr_products (store_id, product_code, name, sku, category, status, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'draft', CURRENT_TIMESTAMP)""",
                    (
                        store["id"], code,
                        request.form.get("name", "").strip() or "Untitled Product",
                        request.form.get("sku", "").strip(),
                        request.form.get("category", "").strip(),
                    ),
                )
            flash("Product QR created.", "success")
        elif action == "duplicate":
            product_id = request.form.get("product_id", type=int)
            product = get_qr_product_or_404(store["id"], product_id)
            with db() as conn:
                code = unique_entity_code(conn, "qr_products", "product_code")
                conn.execute(
                    """INSERT INTO qr_products (store_id, product_code, name, image_url, description, sku, brand,
                       category, specifications, user_manual_url, warranty_info, status, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', CURRENT_TIMESTAMP)""",
                    (
                        store["id"], code, f"{product['name']} (copy)", product["image_url"],
                        product["description"], product["sku"], product["brand"], product["category"],
                        product["specifications"], product["user_manual_url"], product["warranty_info"],
                    ),
                )
            flash("Product duplicated.", "success")
        elif action == "archive":
            product_id = request.form.get("product_id", type=int)
            with db() as conn:
                conn.execute(
                    "UPDATE qr_products SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?",
                    (product_id, store["id"]),
                )
            flash("Product archived.", "success")
        elif action == "delete":
            product_id = request.form.get("product_id", type=int)
            with db() as conn:
                conn.execute("DELETE FROM qr_products WHERE id = ? AND store_id = ?", (product_id, store["id"]))
            flash("Product deleted.", "success")
        elif action == "batch_status":
            ids = [int(v) for v in request.form.get("product_ids", "").split(",") if v.isdigit()]
            status = request.form.get("status", "published")
            if ids and status in QR_ENTITY_STATUSES:
                placeholders = ",".join("?" * len(ids))
                with db() as conn:
                    conn.execute(
                        f"UPDATE qr_products SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE store_id = ? AND id IN ({placeholders})",
                        [status, store["id"], *ids],
                    )
                flash(f"Updated {len(ids)} product(s).", "success")
    products = store_qr_products(store["id"])
    categories = sorted({p["category"] for p in products if p["category"]})
    return render_template(
        "owner/product_qr.html",
        store=store,
        products=products,
        categories=categories,
        entity_statuses=QR_ENTITY_STATUSES,
    )


@app.route("/manage/<slug>/product-qr/<int:product_id>", methods=["GET", "POST"])
@login_required
def manage_product_qr_detail(slug: str, product_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    product = get_qr_product_or_404(store["id"], product_id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update":
            with db() as conn:
                conn.execute(
                    """UPDATE qr_products SET name = ?, image_url = ?, description = ?, sku = ?, brand = ?,
                       category = ?, specifications = ?, user_manual_url = ?, warranty_info = ?, status = ?,
                       updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?""",
                    (
                        request.form.get("name", "").strip() or product["name"],
                        resolve_image_field("image_url", "image_file", product["image_url"]),
                        request.form.get("description", "").strip(),
                        request.form.get("sku", "").strip(),
                        request.form.get("brand", "").strip(),
                        request.form.get("category", "").strip(),
                        request.form.get("specifications", "").strip(),
                        request.form.get("user_manual_url", "").strip(),
                        request.form.get("warranty_info", "").strip(),
                        request.form.get("status", product["status"]),
                        product_id, store["id"],
                    ),
                )
            flash("Product updated.", "success")
        elif action == "regenerate":
            with db() as conn:
                regenerate_entity_code(conn, "qr_products", product_id, store["id"])
            flash("QR code regenerated.", "success")
        return redirect(url_for("manage_product_qr_detail", slug=slug, product_id=product_id))
    product = get_qr_product_or_404(store["id"], product_id)
    qr = entity_qr_payload("product_info_view", product["product_code"])
    return render_template(
        "owner/product_qr_detail.html",
        store=store,
        product=product,
        qr=qr,
        entity_statuses=QR_ENTITY_STATUSES,
    )


@app.get("/manage/<slug>/product-qr/export")
@login_required
def export_product_qr(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    products = store_qr_products(store["id"])
    lines = ["name,sku,brand,category,status,product_code,scans"]
    for p in products:
        lines.append(f'"{p["name"]}","{p["sku"] or ""}","{p["brand"] or ""}","{p["category"] or ""}","{p["status"]}","{p["product_code"]}",{p["scan_count"] or 0}')
    content = "\n".join(lines)
    return app.response_class(content, mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{store["slug"]}-products.csv"',
    })


# --- Check-in ---

@app.route("/checkin/<code>", methods=["GET", "POST"])
def check_in_view(code: str):
    point = check_in_point_by_code(code)
    if not point or point["status"] == "archived":
        abort(404)
    if point["status"] == "draft":
        abort(404)
    checked_in = False
    check_time = None
    message = None
    if request.method == "POST":
        result = perform_check_in(code)
        checked_in = result.get("checked_in", False)
        check_time = result.get("time")
        message = result["message"]
    else:
        increment_scan_count("check_in_points", point["id"])
    scenario_label = dict(CHECKIN_SCENARIOS).get(point["scenario"], point["scenario"])
    return render_template(
        "customer/check_in.html",
        point=point,
        scenario_label=scenario_label,
        checked_in=checked_in,
        check_time=check_time,
        message=message,
        preview_mode=False,
    )


@app.get("/manage/<slug>/preview/checkin/<code>")
@login_required
def check_in_owner_preview(slug: str, code: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    point = check_in_point_by_code(code)
    if not point or point["store_slug"] != slug:
        abort(404)
    scenario_label = dict(CHECKIN_SCENARIOS).get(point["scenario"], point["scenario"])
    return render_template(
        "customer/check_in.html",
        point=point,
        scenario_label=scenario_label,
        checked_in=False,
        check_time=None,
        message=None,
        preview_mode=True,
    )


@app.route("/manage/<slug>/check-in", methods=["GET", "POST"])
@login_required
def manage_check_in(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            with db() as conn:
                code = unique_entity_code(conn, "check_in_points", "point_code")
                conn.execute(
                    """INSERT INTO check_in_points (store_id, point_code, name, location, scenario, status, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'draft', CURRENT_TIMESTAMP)""",
                    (
                        store["id"], code,
                        request.form.get("name", "").strip() or "Untitled Check-in",
                        request.form.get("location", "").strip(),
                        request.form.get("scenario", "visitor"),
                    ),
                )
            flash("Check-in point created.", "success")
        elif action == "duplicate":
            point_id = request.form.get("point_id", type=int)
            point = get_check_in_point_or_404(store["id"], point_id)
            with db() as conn:
                code = unique_entity_code(conn, "check_in_points", "point_code")
                conn.execute(
                    """INSERT INTO check_in_points (store_id, point_code, name, location, description,
                       active_status, opening_hours, notes, scenario, status, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', CURRENT_TIMESTAMP)""",
                    (
                        store["id"], code, f"{point['name']} (copy)", point["location"],
                        point["description"], point["active_status"], point["opening_hours"],
                        point["notes"], point["scenario"],
                    ),
                )
            flash("Check-in point duplicated.", "success")
        elif action == "archive":
            point_id = request.form.get("point_id", type=int)
            with db() as conn:
                conn.execute(
                    "UPDATE check_in_points SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND store_id = ?",
                    (point_id, store["id"]),
                )
            flash("Check-in point archived.", "success")
        elif action == "delete":
            point_id = request.form.get("point_id", type=int)
            with db() as conn:
                conn.execute("DELETE FROM check_in_log WHERE point_id = ?", (point_id,))
                conn.execute("DELETE FROM check_in_points WHERE id = ? AND store_id = ?", (point_id, store["id"]))
            flash("Check-in point deleted.", "success")
    points = store_check_in_points(store["id"])
    total_checkins = sum(check_in_stats(p["id"])["successful"] for p in points)
    return render_template(
        "owner/check_in.html",
        store=store,
        points=points,
        scenarios=CHECKIN_SCENARIOS,
        total_checkins=total_checkins,
        entity_statuses=QR_ENTITY_STATUSES,
    )


@app.route("/manage/<slug>/check-in/<int:point_id>", methods=["GET", "POST"])
@login_required
def manage_check_in_detail(slug: str, point_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    point = get_check_in_point_or_404(store["id"], point_id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update":
            with db() as conn:
                conn.execute(
                    """UPDATE check_in_points SET name = ?, location = ?, description = ?, active_status = ?,
                       opening_hours = ?, notes = ?, scenario = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ? AND store_id = ?""",
                    (
                        request.form.get("name", "").strip() or point["name"],
                        request.form.get("location", "").strip(),
                        request.form.get("description", "").strip(),
                        request.form.get("active_status", "active"),
                        request.form.get("opening_hours", "").strip(),
                        request.form.get("notes", "").strip(),
                        request.form.get("scenario", point["scenario"]),
                        request.form.get("status", point["status"]),
                        point_id, store["id"],
                    ),
                )
            flash("Check-in point updated.", "success")
        elif action == "regenerate":
            with db() as conn:
                regenerate_entity_code(conn, "check_in_points", point_id, store["id"])
            flash("QR code regenerated.", "success")
        return redirect(url_for("manage_check_in_detail", slug=slug, point_id=point_id))
    point = get_check_in_point_or_404(store["id"], point_id)
    stats = check_in_stats(point_id)
    activity = check_in_activity(store["id"], point_id)
    qr = entity_qr_payload("check_in_view", point["point_code"])
    return render_template(
        "owner/check_in_detail.html",
        store=store,
        point=point,
        stats=stats,
        activity=activity,
        qr=qr,
        scenarios=CHECKIN_SCENARIOS,
        entity_statuses=QR_ENTITY_STATUSES,
    )


@app.get("/manage/<slug>/check-in/<int:point_id>/scanner")
@login_required
def check_in_scanner(slug: str, point_id: int):
    store = get_store_or_404(slug)
    require_store_owner(store)
    point = get_check_in_point_or_404(store["id"], point_id)
    stats = check_in_stats(point_id)
    return render_template(
        "owner/check_in_scanner.html",
        store=store,
        point=point,
        stats=stats,
        scanner_boot={"scanUrl": url_for("api_checkin_scan"), "csrf": csrf_token(), "pointCode": point["point_code"]},
    )


@app.get("/manage/<slug>/check-in/export")
@login_required
def export_check_in(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    activity = check_in_activity(store["id"], limit=500)
    lines = ["timestamp,point,location,result"]
    for row in activity:
        lines.append(f'"{row["scanned_at"]}","{row["point_name"]}","{row["location"] or ""}","{row["result"]}"')
    content = "\n".join(lines)
    return app.response_class(content, mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{store["slug"]}-checkins.csv"',
    })


@app.post("/api/checkin/scan")
@login_required
def api_checkin_scan():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or request.form.get("code") or "").strip().lower()
    if not code:
        return jsonify({"result": "invalid", "message": "No code provided"}), 400
    result = perform_check_in(code)
    pt = result.get("point")
    return jsonify({
        "result": result["result"],
        "message": result["message"],
        "checked_in": result.get("checked_in", False),
        "time": result.get("time"),
        "point": {
            "name": pt["name"],
            "location": pt["location"],
        } if pt else None,
    })


@app.post("/api/pass/scan")
@login_required
def api_pass_scan():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or request.form.get("code") or "").strip().lower()
    if not code:
        return jsonify({"result": "invalid", "message": "No code provided"}), 400
    result = check_in_pass(code)
    att = result.get("attendee")
    return jsonify({
        "result": result["result"],
        "message": result["message"],
        "checked_in": result.get("checked_in", False),
        "attendee": {
            "name": att["name"],
            "event_name": att["event_name"],
        } if att else None,
    })


@app.get("/api/qr-image")
def api_qr_image():
    link = request.args.get("url", "").strip()
    if not link:
        abort(400)
    return jsonify({"image": qr_data_uri(link)})


@app.post("/store/<slug>/inquire")
def storefront_inquire(slug: str):
    store = public_store_or_404(slug)
    name = request.form.get("customer_name", "").strip()
    if not name:
        flash("Please enter your name.", "error")
        return redirect(url_for("storefront", slug=slug) + "#sf-contact")
    item_id = request.form.get("item_id", type=int)
    from storefront_platform import save_store_inquiry

    with db() as conn:
        save_store_inquiry(
            conn,
            store["id"],
            customer_name=name,
            customer_email=request.form.get("customer_email", "").strip() or None,
            customer_phone=request.form.get("customer_phone", "").strip() or None,
            message=request.form.get("message", "").strip() or None,
            item_id=item_id,
        )
    flash("Thanks — the store received your message.", "success")
    return redirect(url_for("storefront", slug=slug) + "#sf-contact")


@app.route("/store/<slug>")
def storefront(slug: str):
    store = public_store_or_404(slug)
    ctx = storefront_render_context(
        store,
        preview_mode=False,
        group_filter=request.args.get("group"),
        view=request.args.get("view", "shop"),
        group_in_url="group" in request.args,
    )
    return render_template("customer/storefront.html", **ctx)


@app.get("/store/<slug>/items/<int:item_id>")
def customer_item_detail(slug: str, item_id: int):
    store = public_store_or_404(slug)
    item = get_item_or_404(store["id"], item_id)
    if item["status"] != "published":
        abort(404)
    with db() as conn:
        group_name = None
        if item["group_id"]:
            row = conn.execute("SELECT name FROM item_groups WHERE id = ?", (item["group_id"],)).fetchone()
            group_name = row["name"] if row else None
    back_group = parse_item_group_arg(request.args.get("group"))
    deal = None
    with db() as conn:
        from storefront_platform import deals_map_for_items
        deal = deals_map_for_items(conn, store["id"]).get(item_id)
    return render_template(
        "customer/item_detail.html",
        store=store,
        item=item,
        deal=deal,
        group_name=group_name,
        preview_mode=False,
        back_group=group_query_param(back_group) if back_group else None,
    )


from bos.routes import bos_bp

app.register_blueprint(bos_bp)

from feedback_platform import register_feedback_platform
register_feedback_platform(app)

from feedback_core_platform import register_feedback_core_platform
register_feedback_core_platform(app)

from mvp_responses_platform import register_mvp_responses_platform
register_mvp_responses_platform(app)

from qr_experience_platform import register_qr_experience_platform
register_qr_experience_platform(app)

from qr_experience_runtime import register_qr_experience_runtime
register_qr_experience_runtime(app)

from qr_experience_analytics import register_qr_experience_analytics
register_qr_experience_analytics(app)

from qr_experience_templates import register_qr_experience_templates
register_qr_experience_templates(app)

from qr_experience_workflow import register_qr_experience_workflow
register_qr_experience_workflow(app)

from qr_customer_data import register_qr_customer_data
register_qr_customer_data(app)

from customer_platform import register_customer_platform
register_customer_platform(app)

from workspace_platform import register_workspace_platform
register_workspace_platform(app)

from event_platform import register_event_platform
register_event_platform(app)

from workflow_platform import register_workflow_platform
register_workflow_platform(app)

from bos_modules_platform import register_bos_modules_platform
register_bos_modules_platform(app)

from team_platform import register_team_platform
register_team_platform(app)

from task_platform import register_task_platform
register_task_platform(app)

from contact_platform import register_contact_platform
register_contact_platform(app)

from booking_platform import register_booking_platform
register_booking_platform(app)

from checkin_platform import register_checkin_platform
register_checkin_platform(app)

from calendar_platform import register_calendar_platform
register_calendar_platform(app)

from home_platform import register_home_platform
register_home_platform(app)

from integration_platform import register_integration_platform
register_integration_platform(app)

from integrations.platform import register_integrations_core
register_integrations_core(app)

from google_calendar_plugin import register_google_calendar_plugin
register_google_calendar_plugin(app)

from mobile_platform import register_mobile_platform
register_mobile_platform(app)


@app.errorhandler(404)
def not_found_page(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template("errors/404.html"), 404


if __name__ == "__main__":
    init_db()
    # Prefer 5001 — macOS AirPlay often occupies *:5000 and returns 403.
    port = int(os.environ.get("PORT", "5001"))
    host = os.environ.get("HOST", "0.0.0.0")
    ip = lan_ip()
    print(f" * Local:   http://127.0.0.1:{port}")
    if ip:
        print(f" * Network: http://{ip}:{port}")
        if not os.environ.get("PUBLIC_BASE_URL"):
            print(f" * QR tip:  PUBLIC_BASE_URL=http://{ip}:{port} python3 app.py")
    app.run(debug=True, host=host, port=port)
