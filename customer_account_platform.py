"""Shopper accounts — separate session from merchant login, no 2FA on customer paths."""

from __future__ import annotations

import secrets
import logging
import sqlite3
from functools import wraps

_log = logging.getLogger("app.customer_account")

ACCOUNT_KIND_MERCHANT = "merchant"
ACCOUNT_KIND_CUSTOMER = "customer"

MERCHANT_SESSION_KEYS = (
    "user_id",
    "pending_2fa_user_id",
    "active_workspace_id",
    "delete_account_verified_at",
    "two_factor_setup_secret",
)

MERCHANT_SURFACE_PREFIXES = (
    "/app",
    "/manage",
    "/my-stores",
    "/create",
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/magic-link",
    "/magic-signin",
)

CUSTOMER_ACCOUNT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customer_account_profiles (
    user_id INTEGER PRIMARY KEY,
    display_name TEXT,
    phone TEXT,
    linked_visitor_key TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _now() -> str:
    from datetime import datetime

    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def migrate_customer_account_tables(conn) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "account_kind" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN account_kind TEXT NOT NULL DEFAULT 'merchant'"
        )
    conn.executescript(CUSTOMER_ACCOUNT_SCHEMA_SQL)
    from customer_verification import migrate_verification_tables

    migrate_verification_tables(conn)


def is_customer_auth_path(path: str) -> bool:
    return path.startswith("/account/")


def user_account_kind(row) -> str:
    if not row:
        return ACCOUNT_KIND_MERCHANT
    if "account_kind" not in row.keys() or not row["account_kind"]:
        return ACCOUNT_KIND_MERCHANT
    return str(row["account_kind"])


def user_owns_store(conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM stores WHERE owner_id = ? LIMIT 1",
        (int(user_id),),
    ).fetchone()
    return row is not None


def user_has_customer_profile(conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM customer_account_profiles WHERE user_id = ? LIMIT 1",
        (int(user_id),),
    ).fetchone()
    return row is not None


def customer_hub_intro_seen(conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT hub_intro_seen_at FROM customer_account_profiles WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    return bool(row and row["hub_intro_seen_at"])


def mark_customer_hub_intro_seen(conn, user_id: int) -> None:
    now = _now()
    conn.execute(
        """INSERT INTO customer_account_profiles (user_id, hub_intro_seen_at, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             hub_intro_seen_at = excluded.hub_intro_seen_at,
             updated_at = excluded.updated_at""",
        (int(user_id), now, now),
    )


def is_shopper_only_user(conn, user_row) -> bool:
    """True when this identity is a pure shopper — no business mode."""
    if not user_row:
        return False
    return user_account_kind(user_row) == ACCOUNT_KIND_CUSTOMER


def user_has_shopper_profile(conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT username FROM customer_account_profiles WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    return bool(row and row["username"])


def user_can_use_personal_mode(conn, user_id: int) -> bool:
    row = conn.execute("SELECT account_kind FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not row:
        return False
    if user_account_kind(row) == ACCOUNT_KIND_CUSTOMER:
        return True
    return user_has_shopper_profile(conn, user_id)


def user_can_use_business_mode(conn, user_id: int) -> bool:
    row = conn.execute("SELECT account_kind FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not row:
        return False
    if user_account_kind(row) == ACCOUNT_KIND_MERCHANT:
        return True
    return user_owns_store(conn, user_id)


def clear_merchant_session(flask_session) -> None:
    for key in MERCHANT_SESSION_KEYS:
        flask_session.pop(key, None)


def is_merchant_surface_path(path: str) -> bool:
    if path == "/app/account":
        return True
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in MERCHANT_SURFACE_PREFIXES
    )


def safe_customer_next_url(target: str | None, *, fallback: str = "/home") -> str:
    if not target or not target.startswith("/") or target.startswith("//"):
        return fallback
    if is_merchant_surface_path(target):
        return fallback
    return target


def customer_auth_wants_json() -> bool:
    from flask import request

    return request.headers.get("X-Customer-Auth") == "1"


def customer_auth_json_ok(redirect_url: str):
    from flask import flash, redirect

    if customer_auth_wants_json():
        return {"ok": True, "redirect": redirect_url}
    flash("Welcome back.", "success")
    return redirect(redirect_url)


def customer_auth_json_fail(message: str, *, status: int = 400, template=None, next_url=None):
    from flask import flash, render_template

    if customer_auth_wants_json():
        return {"ok": False, "error": message}, status
    flash(message, "error")
    return render_template(template or "customer/login.html", next_url=next_url)


def current_customer_id(flask_session) -> int | None:
    raw = flask_session.get("customer_user_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        _log.debug("customer_id_parse_failed", exc_info=True, extra={"op": "current_customer_id"})
        return None


def _preserve_guest_session_keys(flask_session) -> dict:
    return {k: flask_session[k] for k in ("visitor_key",) if k in flask_session}


def sign_in_customer(flask_session, user_id: int, *, csrf_fn, remember_device: bool = True) -> None:
    """Shopper login — never leave merchant session keys active."""
    from session_remember import apply_remember_device

    clear_merchant_session(flask_session)
    apply_remember_device(flask_session, remember_device)
    flask_session["customer_user_id"] = int(user_id)
    csrf_fn()


def sign_out_customer(flask_session, *, forget_device: bool = False) -> None:
    from session_remember import REMEMBER_SESSION_KEY

    flask_session.pop("customer_user_id", None)
    if forget_device:
        flask_session.pop(REMEMBER_SESSION_KEY, None)
        flask_session.modified = True


def attach_visitor_to_customer(
    conn,
    visitor_key: str,
    user_id: int,
    *,
    email: str,
    display_name: str | None = None,
    phone: str | None = None,
) -> None:
    from guest_platform import link_guest_email, upsert_guest_profile

    if not visitor_key:
        return
    email_n = (email or "").strip().lower()
    name = (display_name or "").strip() or None
    phone_n = (phone or "").strip() or None
    now = _now()
    conn.execute(
        """INSERT INTO customer_account_profiles (user_id, display_name, phone, linked_visitor_key, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             display_name = COALESCE(excluded.display_name, customer_account_profiles.display_name),
             phone = COALESCE(excluded.phone, customer_account_profiles.phone),
             linked_visitor_key = COALESCE(excluded.linked_visitor_key, customer_account_profiles.linked_visitor_key),
             updated_at = excluded.updated_at""",
        (user_id, name, phone_n, visitor_key, now),
    )
    if email_n:
        link_guest_email(conn, email_n, visitor_key)
    upsert_guest_profile(conn, visitor_key, display_name=name, email=email_n, phone=phone_n)


def customer_contact_hints(conn, customer_user_id: int) -> dict[str, str]:
    row = conn.execute(
        """SELECT u.email, p.display_name, p.phone
           FROM users u
           LEFT JOIN customer_account_profiles p ON p.user_id = u.id
           WHERE u.id = ?""",
        (customer_user_id,),
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


def effective_contact_hints(conn, visitor_key: str, customer_user_id: int | None) -> dict[str, str]:
    if customer_user_id:
        hints = customer_contact_hints(conn, customer_user_id)
        if hints:
            return hints
    from guest_platform import guest_contact_hints

    return guest_contact_hints(conn, visitor_key)


def _safe_next_url(target: str | None, *, fallback: str = "/home") -> str:
    return safe_customer_next_url(target, fallback=fallback)


def ensure_shopper_account_kind(conn, user_id: int) -> None:
    conn.execute(
        "UPDATE users SET account_kind = ? WHERE id = ?",
        (ACCOUNT_KIND_CUSTOMER, int(user_id)),
    )


def register_customer_account_platform(app) -> None:
    from flask import flash, redirect, render_template, request, session, url_for
    from werkzeug.security import check_password_hash, generate_password_hash

    from app import consume_auth_token, create_auth_token, csrf_token, db, verify_firebase_token
    from guest_platform import ensure_visitor_key

    def get_customer():
        cid = current_customer_id(session)
        if not cid:
            return None
        with db() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (cid,)).fetchone()
            if not row:
                sign_out_customer(session)
                return None
            if user_can_use_personal_mode(conn, int(row["id"])):
                return row
        sign_out_customer(session)
        return None

    def customer_login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not get_customer():
                from flask import flash, redirect, request, url_for

                flash("Please sign in to your shopper account.", "error")
                return redirect(
                    url_for(
                        "customer_account_home",
                        open="login",
                        next=request.path,
                    )
                )
            return view(*args, **kwargs)

        return wrapped

    def finish_customer_sign_in(
        user_id: int,
        *,
        email: str,
        display_name: str | None = None,
        remember_device: bool = True,
    ) -> None:
        visitor_key = ensure_visitor_key(session)
        with db() as conn:
            attach_visitor_to_customer(
                conn, visitor_key, user_id, email=email, display_name=display_name,
            )
        sign_in_customer(session, user_id, csrf_fn=csrf_token, remember_device=remember_device)

    @app.route("/account/register", methods=["GET", "POST"])
    def customer_register():
        next_url = request.args.get("next") or request.form.get("next")
        if get_customer():
            return redirect(_safe_next_url(next_url))
        if request.method == "GET":
            return redirect(url_for("customer_account_home", open="signup", next=next_url))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            display_name = request.form.get("display_name", "").strip() or None
            if not request.form.get("legal_consent"):
                return customer_auth_json_fail(
                    "Please accept the Terms of Service and Privacy Policy to continue.",
                    template="customer/register.html",
                    next_url=next_url,
                )
            if "@" not in email or len(email) > 254:
                return customer_auth_json_fail(
                    "Enter a valid email address.",
                    template="customer/register.html",
                    next_url=next_url,
                )
            if len(password) < 12:
                return customer_auth_json_fail(
                    "Use a password with at least 12 characters.",
                    template="customer/register.html",
                    next_url=next_url,
                )
            if password != confirm:
                return customer_auth_json_fail(
                    "Your passwords do not match.",
                    template="customer/register.html",
                    next_url=next_url,
                )
            try:
                with db() as conn:
                    cur = conn.execute(
                        """INSERT INTO users (email, password_hash, account_kind)
                           VALUES (?, ?, ?)""",
                        (
                            email,
                            generate_password_hash(password, method="pbkdf2:sha256:600000"),
                            ACCOUNT_KIND_CUSTOMER,
                        ),
                    )
                    user_id = int(cur.lastrowid)
                from session_remember import parse_remember_device

                finish_customer_sign_in(
                    user_id,
                    email=email,
                    display_name=display_name,
                    remember_device=parse_remember_device(request.form.get("remember_device")),
                )
                if customer_auth_wants_json():
                    return {"ok": True, "redirect": _safe_next_url(next_url)}
                flash("Welcome! You're signed in.", "success")
                return redirect(_safe_next_url(next_url))
            except sqlite3.IntegrityError:
                with db() as conn:
                    existing = conn.execute(
                        "SELECT account_kind FROM users WHERE email = ?", (email,)
                    ).fetchone()
                if existing and user_account_kind(existing) == ACCOUNT_KIND_MERCHANT:
                    return customer_auth_json_fail(
                        "This email is used for a business account. Use another email for shopping.",
                        template="customer/register.html",
                        next_url=next_url,
                    )
                return customer_auth_json_fail(
                    "An account with that email already exists. Please sign in.",
                    template="customer/register.html",
                    next_url=next_url,
                )
        return render_template(
            "customer/register.html",
            next_url=next_url,
        )

    @app.route("/account/login", methods=["GET", "POST"])
    def customer_login():
        from customer_verification import find_user_by_login

        next_url = request.args.get("next") or request.form.get("next")
        if get_customer():
            return redirect(_safe_next_url(next_url))
        if request.method == "GET":
            return redirect(url_for("customer_account_home", open="login", next=next_url))
        identifier = request.form.get("email", "").strip() or request.form.get("identifier", "").strip()
        with db() as conn:
            user = find_user_by_login(conn, identifier)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            with db() as conn:
                uid = int(user["id"])
                if user_account_kind(user) == ACCOUNT_KIND_MERCHANT and not user_has_shopper_profile(conn, uid):
                    return customer_auth_json_fail(
                        "No shopper profile yet. Use Sign up to activate personal mode.",
                        template="customer/login.html",
                        next_url=next_url,
                    )
            login_email = user["email"]
            from customer_verification import is_synthetic_customer_email

            if is_synthetic_customer_email(login_email) and user["phone"]:
                login_email = user["phone"]
            from session_remember import parse_remember_device

            finish_customer_sign_in(
                uid,
                email=login_email,
                remember_device=parse_remember_device(request.form.get("remember_device")),
            )
            return customer_auth_json_ok(_safe_next_url(next_url))
        return customer_auth_json_fail(
            "Email, phone, or password is incorrect.",
            template="customer/login.html",
            next_url=next_url,
        )

    @app.post("/account/switch/business")
    def customer_switch_to_business():
        from app import sign_in_user

        cid = current_customer_id(session)
        if not cid:
            flash("Sign in to your personal account first.", "error")
            return redirect(url_for("customer_account_home", open="login"))
        with db() as conn:
            if not user_can_use_business_mode(conn, cid):
                flash("This account does not have a business profile.", "error")
                return redirect(url_for("index"))
        sign_in_user(int(cid))
        flash("Switched to Business mode.", "success")
        return redirect(url_for("bos.store"))

    @app.post("/account/switch/personal")
    def customer_switch_to_personal():
        uid = session.get("user_id")
        if not uid:
            flash("Sign in to your business account first.", "error")
            return redirect(url_for("login"))
        with db() as conn:
            from customer_verification import customer_needs_onboarding

            if not user_can_use_personal_mode(conn, int(uid)):
                flash("Activate personal mode first — sign up with the same email.", "info")
                return redirect(url_for("customer_account_home", open="signup"))
            needs = customer_needs_onboarding(conn, int(uid))
        sign_in_customer(session, int(uid), csrf_fn=csrf_token)
        flash("Switched to Personal mode.", "success")
        if needs:
            return redirect(url_for("customer_account_home"))
        return redirect(url_for("index"))

    @app.post("/account/logout")
    def customer_logout():
        sign_out_customer(session, forget_device=True)
        flash("Signed out of your shopper account.", "success")
        return redirect(_safe_next_url(request.form.get("next") or request.referrer))

    @app.post("/auth/firebase/customer")
    def firebase_customer_login():
        return {"error": "Google sign-in has been removed. Use phone verification."}, 410

    @app.route("/account/forgot-password", methods=["GET", "POST"])
    def customer_forgot_password():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            with db() as conn:
                user = conn.execute(
                    "SELECT id, account_kind FROM users WHERE email = ?", (email,)
                ).fetchone()
            if user and user_account_kind(user) == ACCOUNT_KIND_CUSTOMER:
                token = create_auth_token(user["id"], "reset_customer")
                _log.warning("customer_reset_link_sent token_prefix=%s", token[:8])
            flash("If that email has a shopper account, a reset link has been sent.", "success")
            return redirect(url_for("customer_login"))
        return render_template("customer/forgot_password.html")

    @app.route("/account/reset-password/<token>", methods=["GET", "POST"])
    def customer_reset_password(token: str):
        if request.method == "POST":
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if len(password) < 12 or password != confirm:
                flash("Use matching passwords with at least 12 characters.", "error")
            else:
                auth_token = consume_auth_token(token, "reset_customer")
                if not auth_token:
                    flash("This reset link is invalid or expired.", "error")
                    return redirect(url_for("customer_forgot_password"))
                with db() as conn:
                    user = conn.execute(
                        "SELECT account_kind FROM users WHERE id = ?", (auth_token["user_id"],),
                    ).fetchone()
                    if not user or user_account_kind(user) != ACCOUNT_KIND_CUSTOMER:
                        flash("Invalid reset link for shopper account.", "error")
                        return redirect(url_for("customer_forgot_password"))
                    conn.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (
                            generate_password_hash(password, method="pbkdf2:sha256:600000"),
                            auth_token["user_id"],
                        ),
                    )
                flash("Password changed. You can now sign in.", "success")
                return redirect(url_for("customer_login"))
        return render_template("customer/reset_password.html", token=token)

    @app.route("/account/magic-link", methods=["GET", "POST"])
    def customer_magic_link():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            with db() as conn:
                user = conn.execute(
                    "SELECT id, account_kind FROM users WHERE email = ?", (email,)
                ).fetchone()
            if user and user_account_kind(user) == ACCOUNT_KIND_CUSTOMER:
                token = create_auth_token(user["id"], "magic_customer")
                _log.warning("customer_magic_link_sent token_prefix=%s", token[:8])
            flash("If that email has a shopper account, a sign-in link has been sent.", "success")
            return redirect(url_for("customer_login"))
        return render_template("customer/magic_link.html")

    @app.get("/account/magic-signin/<token>")
    def customer_magic_signin(token: str):
        auth_token = consume_auth_token(token, "magic_customer")
        if not auth_token:
            flash("This sign-in link is invalid or expired.", "error")
            return redirect(url_for("customer_login"))
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (auth_token["user_id"],)).fetchone()
        if not user or user_account_kind(user) != ACCOUNT_KIND_CUSTOMER:
            flash("Invalid sign-in link for shopper account.", "error")
            return redirect(url_for("customer_login"))
        finish_customer_sign_in(int(user["id"]), email=user["email"])
        flash("You're signed in.", "success")
        return redirect(url_for("index"))

    @app.get("/account")
    def customer_account_home():
        customer = get_customer()
        if not customer:
            return render_template("customer/account_guest.html", preview_mode=False)
        with db() as conn:
            profile = conn.execute(
                """SELECT display_name, phone, username, avatar_url, bio
                   FROM customer_account_profiles WHERE user_id = ?""",
                (customer["id"],),
            ).fetchone()
            from guest_platform import recent_store_count
            from customer_verification import customer_needs_onboarding, generate_username

            places = recent_store_count(conn, ensure_visitor_key(session))
            if customer_needs_onboarding(conn, int(customer["id"])):
                return render_template(
                    "customer/account_setup.html",
                    preview_mode=False,
                    suggested_username=generate_username(conn),
                    customer=customer,
                )
        profile_d = dict(profile) if profile else {}
        display = profile_d.get("display_name") or profile_d.get("username") or customer["email"].split("@")[0]
        public_email = customer["email"]
        from customer_verification import is_synthetic_customer_email

        if is_synthetic_customer_email(public_email):
            public_email = profile_d.get("phone") or "Phone account"
        return render_template(
            "customer/account.html",
            customer=customer,
            profile=profile_d,
            places_count=places,
            display_name=display,
            public_email=public_email,
        )

    @app.post("/account")
    @customer_login_required
    def customer_account_update():
        from app import save_uploaded_image, resolve_image_field
        from customer_verification import username_available, validate_username

        customer = get_customer()
        display_name = request.form.get("display_name", "").strip() or None
        phone = request.form.get("phone", "").strip() or None
        bio = request.form.get("bio", "").strip() or None
        username_raw = (request.form.get("username") or "").strip().lower()
        username = validate_username(username_raw) if username_raw else None
        try:
            avatar_url = resolve_image_field("avatar_url", "avatar", None)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("customer_account_home"))
        with db() as conn:
            if username:
                if not username_available(conn, username, exclude_user_id=int(customer["id"])):
                    flash("That username is taken.", "error")
                    return redirect(url_for("customer_account_home"))
            row = conn.execute(
                "SELECT username, avatar_url FROM customer_account_profiles WHERE user_id = ?",
                (customer["id"],),
            ).fetchone()
            existing = dict(row) if row else {}
            now = _now()
            conn.execute(
                """INSERT INTO customer_account_profiles
                   (user_id, display_name, phone, username, avatar_url, bio, linked_visitor_key, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     display_name = COALESCE(excluded.display_name, customer_account_profiles.display_name),
                     phone = COALESCE(excluded.phone, customer_account_profiles.phone),
                     username = COALESCE(excluded.username, customer_account_profiles.username),
                     avatar_url = COALESCE(excluded.avatar_url, customer_account_profiles.avatar_url),
                     bio = COALESCE(excluded.bio, customer_account_profiles.bio),
                     linked_visitor_key = COALESCE(excluded.linked_visitor_key, customer_account_profiles.linked_visitor_key),
                     updated_at = excluded.updated_at""",
                (
                    int(customer["id"]),
                    display_name,
                    phone,
                    username or existing.get("username"),
                    avatar_url or existing.get("avatar_url"),
                    bio,
                    ensure_visitor_key(session),
                    now,
                ),
            )
            attach_visitor_to_customer(
                conn,
                ensure_visitor_key(session),
                int(customer["id"]),
                email=customer["email"],
                display_name=display_name,
                phone=phone,
            )
        flash("Your profile was updated.", "success")
        return redirect(url_for("customer_account_home"))

    @app.post("/api/customer/hub-intro-seen")
    def customer_hub_intro_seen_api():
        customer = get_customer()
        if not customer:
            return {"ok": False, "error": "Sign in required."}, 401
        with db() as conn:
            migrate_customer_account_tables(conn)
            mark_customer_hub_intro_seen(conn, int(customer["id"]))
        return {"ok": True}

    from customer_verification import register_customer_verification_routes

    register_customer_verification_routes(
        app,
        db=db,
        get_customer=get_customer,
        finish_customer_sign_in=finish_customer_sign_in,
        customer_auth_wants_json=customer_auth_wants_json,
        _safe_next_url=_safe_next_url,
        user_account_kind=user_account_kind,
        ACCOUNT_KIND_CUSTOMER=ACCOUNT_KIND_CUSTOMER,
        ACCOUNT_KIND_MERCHANT=ACCOUNT_KIND_MERCHANT,
        user_owns_store=user_owns_store,
        ensure_shopper_account_kind=ensure_shopper_account_kind,
        sign_in_customer=sign_in_customer,
        csrf_token=csrf_token,
        attach_visitor_to_customer=attach_visitor_to_customer,
        ensure_visitor_key=ensure_visitor_key,
        user_has_customer_profile=user_has_customer_profile,
    )
