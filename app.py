from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import secrets
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

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
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
        if not current_user():
            flash("Please sign in to manage a storefront.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def protect_forms():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
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


@app.route("/")
def index():
    if current_user():
        return redirect(url_for("bos.home"))
    return redirect(url_for("login"))


def sign_in_user(user_id: int):
    session.clear()
    session["user_id"] = user_id
    csrf_token()


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("bos.home"))
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
                return redirect(url_for("bos.home"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists. Please sign in.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("bos.home"))
    if request.method == "POST":
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (request.form.get("email", "").strip().lower(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            if user["two_factor_secret"]:
                session["pending_2fa_user_id"] = user["id"]
                return redirect(url_for("two_factor_login"))
            sign_in_user(user["id"])
            destination = request.args.get("next", "")
            return redirect(destination if destination.startswith("/") and not destination.startswith("//") else url_for("bos.home"))
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
            user = {"id": cursor.lastrowid, "two_factor_secret": None}
    if user["two_factor_secret"]:
        session["pending_2fa_user_id"] = user["id"]
        return {"next": url_for("two_factor_login")}
    sign_in_user(user["id"])
    intent = payload.get("intent", "login")
    if is_new and intent == "signup":
        return {"next": url_for("bos.home")}
    return {"next": url_for("bos.home")}


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
            return redirect(url_for("bos.home"))
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
    return redirect(url_for("bos.home"))


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
        return render_template("two_factor_settings.html", enabled=True)
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
    return render_template("two_factor_settings.html", enabled=False, secret=secret, qr_image=qr_data_uri(uri))


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
    owner_id = current_user()["id"]
    return render_template(
        "owner/my_stores.html",
        workspace=workspace_snapshot(owner_id),
        workspace_mode="all",
    )


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
    primary_qr_image = qr_data_uri(url_for("qr_entry", code=primary_qr["code"], _external=True)) if primary_qr else None
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
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("store_settings", slug=slug))
        with db() as conn:
            conn.execute(
                """UPDATE stores SET name = ?, description = ?, owner_name = ?, contact = ?, address = ?,
                   business_hours = ?, background_image = ?, group_id = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (
                    request.form.get("name", "").strip() or store["name"],
                    request.form.get("description", "").strip(),
                    request.form.get("owner_name", "").strip(),
                    request.form.get("contact", "").strip(),
                    request.form.get("address", "").strip(),
                    request.form.get("business_hours", "").strip(),
                    background_image,
                    request.form.get("group_id") or None,
                    store["id"],
                ),
            )
        flash("Store settings saved.", "success")
        return redirect(url_for("store_settings", slug=slug))
    return render_template(
        "owner/store_settings.html",
        store=store,
        store_groups=owner_store_groups(current_user()["id"]),
    )


@app.get("/manage/<slug>/preview")
@login_required
def store_preview(slug: str):
    store = get_store_or_404(slug)
    require_store_owner(store)
    group_filter = request.args.get("group")
    active_group, group_nav, show_group_nav, active_group_name = resolve_item_group_context(store["id"], group_filter, published_only=True)
    items = customer_items(store["id"], active_group)
    return render_template(
        "customer/storefront.html",
        store=store,
        items=items,
        group_nav=group_nav,
        show_group_nav=show_group_nav,
        active_group=active_group,
        active_group_name=active_group_name,
        preview_mode=True,
    )


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
            "url": url_for("qr_entry", code=qr["code"], _external=True),
            "image": qr_data_uri(url_for("qr_entry", code=qr["code"], _external=True)),
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
    return render_template(
        "customer/storefront.html",
        store=store,
        items=customer_items(store["id"], active_group),
        group_nav=group_nav,
        show_group_nav=show_group_nav,
        active_group=active_group,
        active_group_name=active_group_name,
        preview_mode=True,
        qr_label=qr["name"],
    )


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
    return render_template(
        "customer/item_detail.html",
        store=store,
        item=preview_item,
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
    with db() as conn:
        qr = conn.execute(
            "SELECT qr_codes.*, stores.slug, stores.status FROM qr_codes JOIN stores ON qr_codes.store_id = stores.id WHERE qr_codes.code = ?",
            (code,),
        ).fetchone()
    if not qr or qr["status"] == "archived":
        abort(404)
    return redirect(url_for("storefront", slug=qr["slug"], qr=code))


@app.route("/store/<slug>")
def storefront(slug: str):
    store = public_store_or_404(slug)
    group_filter = request.args.get("group")
    active_group, group_nav, show_group_nav, active_group_name = resolve_item_group_context(store["id"], group_filter, published_only=True)
    items = customer_items(store["id"], active_group)
    return render_template(
        "customer/storefront.html",
        store=store,
        items=items,
        group_nav=group_nav,
        show_group_nav=show_group_nav,
        active_group=active_group,
        active_group_name=active_group_name,
        preview_mode=False,
    )


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
    return render_template(
        "customer/item_detail.html",
        store=store,
        item=item,
        group_name=group_name,
        preview_mode=False,
        back_group=group_query_param(back_group) if back_group else None,
    )


from bos.routes import bos_bp

app.register_blueprint(bos_bp)


if __name__ == "__main__":
    import os
    init_db()
    # Prefer 5001 — macOS AirPlay often occupies *:5000 and returns 403.
    port = int(os.environ.get("PORT", "5001"))
    app.run(debug=True, port=port)
