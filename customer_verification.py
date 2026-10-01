"""Email / phone OTP verification and shopper onboarding helpers."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta

_log = logging.getLogger("app.customer_verification")

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
OTP_HOURLY_LIMIT = 8
ONBOARDING_TTL_MINUTES = 20

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_.]{2,29}$")
PHONE_DIGITS_RE = re.compile(r"^\+\d{8,15}$")

VERIFICATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customer_verification_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    target TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT 'signup',
    code_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cvc_lookup
    ON customer_verification_codes(channel, target, purpose, created_at DESC);
"""

PROFILE_EXTRA_COLUMNS = (
    ("username", "TEXT"),
    ("avatar_url", "TEXT"),
    ("bio", "TEXT"),
    ("hub_intro_seen_at", "TEXT"),
)


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _expires(minutes: int) -> str:
    return (datetime.utcnow() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def normalize_email(raw: str) -> str | None:
    email = (raw or "").strip().lower()
    if "@" not in email or len(email) > 254:
        return None
    return email


def normalize_phone(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    digits = re.sub(r"[^\d+]", "", text)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        digits = "+" + digits.lstrip("0")
    if not PHONE_DIGITS_RE.match(digits):
        return None
    return digits


def mask_target(channel: str, target: str) -> str:
    if channel == "email" and "@" in target:
        local, domain = target.split("@", 1)
        if len(local) <= 2:
            masked = local[0] + "***"
        else:
            masked = local[0] + "***" + local[-1]
        return f"{masked}@{domain}"
    if channel == "phone" and len(target) > 4:
        return target[:3] + "***" + target[-2:]
    return target


def phone_placeholder_email(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return f"phone+{digits}@customers.zintriq.local"


def is_synthetic_customer_email(email: str | None) -> bool:
    value = (email or "").lower()
    return value.endswith("@customers.zintriq.local") or value.endswith(
        "@customers.marketqr.local"
    )


def migrate_verification_tables(conn) -> None:
    conn.executescript(VERIFICATION_SCHEMA_SQL)
    user_cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "phone" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone) WHERE phone IS NOT NULL"
    )
    profile_cols = {row["name"] for row in conn.execute("PRAGMA table_info(customer_account_profiles)").fetchall()}
    for name, col_type in PROFILE_EXTRA_COLUMNS:
        if name not in profile_cols:
            conn.execute(f"ALTER TABLE customer_account_profiles ADD COLUMN {name} {col_type}")
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_username
           ON customer_account_profiles(username) WHERE username IS NOT NULL"""
    )
    conn.execute(
        """DELETE FROM customer_account_profiles
           WHERE user_id NOT IN (SELECT id FROM users)"""
    )


def validate_username(raw: str) -> str | None:
    username = (raw or "").strip().lower()
    if not USERNAME_RE.match(username):
        return None
    return username


def generate_username(conn) -> str:
    for _ in range(24):
        suffix = secrets.token_hex(2)
        candidate = f"shopper_{suffix}"
        if username_available(conn, candidate):
            return candidate
    return f"shopper_{secrets.token_hex(4)}"


def username_available(conn, username: str, *, exclude_user_id: int | None = None) -> bool:
    row = conn.execute(
        """SELECT p.user_id FROM customer_account_profiles p
           INNER JOIN users u ON u.id = p.user_id
           WHERE p.username = ?""",
        (username,),
    ).fetchone()
    if not row:
        return True
    if exclude_user_id and int(row["user_id"]) == int(exclude_user_id):
        return True
    return False


def _recent_send_count(conn, channel: str, target: str) -> int:
    since = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        """SELECT COUNT(*) AS n FROM customer_verification_codes
           WHERE channel = ? AND target = ? AND created_at >= ?""",
        (channel, target, since),
    ).fetchone()
    return int(row["n"]) if row else 0


def _latest_code_row(conn, channel: str, target: str, purpose: str):
    return conn.execute(
        """SELECT * FROM customer_verification_codes
           WHERE channel = ? AND target = ? AND purpose = ?
           ORDER BY id DESC LIMIT 1""",
        (channel, target, purpose),
    ).fetchone()


def generate_otp_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def deliver_otp(app, *, channel: str, target: str, code: str) -> None:
    label = "Zintriq"
    if channel == "email":
        subject = f"{label} verification code"
        body = f"Your verification code is {code}. It expires in {OTP_TTL_MINUTES} minutes."
        _deliver_email(app, target, subject, body)
        return
    body = f"{label}: your verification code is {code}"
    _deliver_sms(app, target, body)


def _deliver_email(app, to: str, subject: str, body: str) -> None:
    to_domain = to.split("@", 1)[1] if "@" in to else "unknown"
    _log.warning("verification_email_send to_domain=%s body_len=%d", to_domain, len(body))


def _deliver_sms(app, phone: str, body: str) -> None:
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
    if sid and token and from_num:
        try:
            from twilio.rest import Client

            Client(sid, token).messages.create(to=phone, from_=from_num, body=body)
            return
        except Exception as exc:
            _log.warning("twilio_sms_failed error=%s", type(exc).__name__)
    _log.warning("verification_sms_fallback body_len=%d", len(body))


def send_verification_code(app, conn, *, channel: str, target: str, purpose: str = "signup") -> tuple[bool, str, dict | None]:
    if _recent_send_count(conn, channel, target) >= OTP_HOURLY_LIMIT:
        return False, "Too many codes sent. Try again later.", None

    latest = _latest_code_row(conn, channel, target, purpose)
    if latest:
        created = datetime.strptime(latest["created_at"], "%Y-%m-%d %H:%M:%S")
        if (datetime.utcnow() - created).total_seconds() < OTP_RESEND_SECONDS:
            return False, "Wait a moment before requesting another code.", None

    code = generate_otp_code()
    conn.execute(
        "DELETE FROM customer_verification_codes WHERE channel = ? AND target = ? AND purpose = ?",
        (channel, target, purpose),
    )
    conn.execute(
        """INSERT INTO customer_verification_codes
           (channel, target, purpose, code_hash, attempts, expires_at, created_at)
           VALUES (?, ?, ?, ?, 0, ?, ?)""",
        (channel, target, purpose, hash_otp(code), _expires(OTP_TTL_MINUTES), _now()),
    )
    deliver_otp(app, channel=channel, target=target, code=code)
    return True, "Verification code sent.", {
        "channel": channel,
        "target": target,
        "masked": mask_target(channel, target),
        "purpose": purpose,
        "resend_seconds": OTP_RESEND_SECONDS,
    }


def verify_code(conn, *, channel: str, target: str, code: str, purpose: str = "signup") -> tuple[bool, str]:
    row = _latest_code_row(conn, channel, target, purpose)
    if not row:
        return False, "No active code. Request a new one."
    if row["expires_at"] <= _now():
        return False, "This code expired. Request a new one."
    attempts = int(row["attempts"]) + 1
    conn.execute(
        "UPDATE customer_verification_codes SET attempts = ? WHERE id = ?",
        (attempts, row["id"]),
    )
    if attempts > OTP_MAX_ATTEMPTS:
        return False, "Too many attempts. Request a new code."
    if not secrets.compare_digest(row["code_hash"], hash_otp(code.strip())):
        return False, "Incorrect code. Try again."
    conn.execute("DELETE FROM customer_verification_codes WHERE id = ?", (row["id"],))
    return True, "Verified."


def set_verified_identity(
    session,
    *,
    channel: str,
    target: str,
    mode: str = "new",
    user_id: int | None = None,
) -> None:
    session["customer_verified_identity"] = {
        "channel": channel,
        "target": target,
        "mode": mode,
        "user_id": int(user_id) if user_id else None,
        "expires_at": _expires(ONBOARDING_TTL_MINUTES),
    }


def pop_verified_identity(session) -> dict | None:
    raw = session.pop("customer_verified_identity", None)
    if not raw:
        return None
    if raw.get("expires_at", "") <= _now():
        return None
    return raw


def peek_verified_identity(session) -> dict | None:
    raw = session.get("customer_verified_identity")
    if not raw:
        return None
    if raw.get("expires_at", "") <= _now():
        session.pop("customer_verified_identity", None)
        return None
    return raw


def find_user_by_contact(conn, channel: str, target: str):
    if channel == "email":
        return conn.execute("SELECT * FROM users WHERE email = ?", (target,)).fetchone()
    return conn.execute(
        "SELECT * FROM users WHERE phone = ? OR email = ?",
        (target, phone_placeholder_email(target)),
    ).fetchone()


def evaluate_signup_contact(
    conn,
    user,
    *,
    user_account_kind,
    user_owns_store,
    user_has_customer_profile,
    ACCOUNT_KIND_CUSTOMER,
    ACCOUNT_KIND_MERCHANT,
) -> dict:
    """Decide whether signup should create, activate shopper, or block."""
    if not user:
        return {"status": "new"}
    uid = int(user["id"])
    kind = user_account_kind(user)
    has_profile = user_has_customer_profile(conn, uid)
    needs_profile = customer_needs_onboarding(conn, uid)
    if kind == ACCOUNT_KIND_CUSTOMER and not needs_profile:
        return {"status": "exists", "error": "An account already exists. Sign in instead."}
    if kind == ACCOUNT_KIND_MERCHANT and has_profile and not needs_profile:
        return {"status": "exists", "error": "An account already exists. Sign in instead."}
    if kind == ACCOUNT_KIND_MERCHANT:
        return {"status": "activate", "user_id": uid}
    return {"status": "resume", "user_id": uid}


def find_user_by_login(conn, identifier: str):
    email = normalize_email(identifier)
    if email:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    phone = normalize_phone(identifier)
    if phone:
        row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        if row:
            return row
        placeholder = phone_placeholder_email(phone)
        return conn.execute("SELECT * FROM users WHERE email = ?", (placeholder,)).fetchone()
    return None


def customer_needs_onboarding(conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT username FROM customer_account_profiles WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    return not row or not row["username"]


def register_customer_verification_routes(app, *, db, get_customer, finish_customer_sign_in, customer_auth_wants_json, _safe_next_url, user_account_kind, ACCOUNT_KIND_CUSTOMER, ACCOUNT_KIND_MERCHANT, user_owns_store, ensure_shopper_account_kind, sign_in_customer, csrf_token, attach_visitor_to_customer, ensure_visitor_key, user_has_customer_profile):
    from flask import jsonify, request, session, url_for

    from customer_account_platform import customer_auth_json_fail, customer_auth_json_ok

    def json_or_error(message: str, status: int = 400):
        if customer_auth_wants_json() or request.is_json:
            return {"ok": False, "error": message}, status
        from flask import flash, redirect, url_for

        flash(message, "error")
        return redirect(url_for("customer_account_home"))

    @app.post("/account/verify/send")
    def customer_verify_send():
        payload = request.get_json(silent=True) or {}
        channel = (payload.get("channel") or request.form.get("channel") or "").strip().lower()
        purpose = (payload.get("purpose") or request.form.get("purpose") or "signup").strip().lower()
        if purpose not in ("signup", "login", "link_email"):
            purpose = "signup"
        raw_target = payload.get("target") or request.form.get("target") or ""
        if purpose == "signup":
            if channel == "email":
                return json_or_error(
                    "Sign up with your phone number first. You can link an email after registration."
                )
            channel = "phone"
            target = normalize_phone(raw_target)
            if not target:
                return json_or_error(
                    "Enter a valid phone number with country code (e.g. +60123456789)."
                )
            consent = payload.get("legal_consent") or request.form.get("legal_consent")
            if not consent or str(consent).lower() in ("0", "false", "no", "off"):
                return json_or_error("Please accept the Terms of Service and Privacy Policy to continue.")
        elif channel == "email":
            target = normalize_email(raw_target)
            if not target:
                return json_or_error("Enter a valid email address.")
        elif channel == "phone":
            target = normalize_phone(raw_target)
            if not target:
                return json_or_error(
                    "Enter a valid phone number with country code (e.g. +60123456789)."
                )
        else:
            return json_or_error("Use your phone number to sign in.")

        signup_eligibility = None
        with db() as conn:
            migrate_verification_tables(conn)
            if purpose == "login":
                user = find_user_by_login(conn, target)
                if not user:
                    return json_or_error("No shopper account found for this contact.")
                if channel == "email" and is_synthetic_customer_email(user["email"]):
                    return json_or_error(
                        "Use your phone number to sign in, or link an email in Account first."
                    )
                uid = int(user["id"])
                from customer_account_platform import user_can_use_personal_mode, user_has_shopper_profile

                if not user_has_shopper_profile(conn, uid) and user_account_kind(user) == ACCOUNT_KIND_MERCHANT:
                    return json_or_error(
                        "No personal profile yet. Use Sign up to activate shopping on this phone."
                    )
                if not user_can_use_personal_mode(conn, uid):
                    return json_or_error("No shopper account found for this contact.")
            elif purpose == "signup":
                existing = find_user_by_contact(conn, channel, target)
                signup_eligibility = evaluate_signup_contact(
                    conn,
                    existing,
                    user_account_kind=user_account_kind,
                    user_owns_store=user_owns_store,
                    user_has_customer_profile=user_has_customer_profile,
                    ACCOUNT_KIND_CUSTOMER=ACCOUNT_KIND_CUSTOMER,
                    ACCOUNT_KIND_MERCHANT=ACCOUNT_KIND_MERCHANT,
                )
                if signup_eligibility["status"] == "blocked":
                    return json_or_error(signup_eligibility["error"])
                if signup_eligibility["status"] == "exists":
                    return json_or_error(signup_eligibility["error"])

            ok, message, meta = send_verification_code(app, conn, channel=channel, target=target, purpose=purpose)
            if not ok:
                return json_or_error(message, 429)
            if signup_eligibility and signup_eligibility["status"] == "activate":
                meta = meta or {}
                meta["mode"] = "activate"
                meta["hint"] = "We'll add personal shopping to this phone — same account, two modes."
        body = {"ok": True, "message": message, **(meta or {})}
        return jsonify(body) if customer_auth_wants_json() or request.is_json else body

    @app.post("/account/verify/check")
    def customer_verify_check():
        payload = request.get_json(silent=True) or {}
        channel = (payload.get("channel") or request.form.get("channel") or "").strip().lower()
        purpose = (payload.get("purpose") or request.form.get("purpose") or "signup").strip().lower()
        code = (payload.get("code") or request.form.get("code") or "").strip()
        raw_target = payload.get("target") or request.form.get("target") or ""
        if channel == "email":
            target = normalize_email(raw_target)
        elif channel == "phone":
            target = normalize_phone(raw_target)
        else:
            return json_or_error("Choose email or phone.")
        if not target or not code.isdigit() or len(code) != OTP_LENGTH:
            return json_or_error("Enter the 6-digit code.")

        with db() as conn:
            migrate_verification_tables(conn)
            ok, message = verify_code(conn, channel=channel, target=target, code=code, purpose=purpose)
            if not ok:
                return json_or_error(message)

            if purpose == "login":
                user = find_user_by_login(conn, target)
                if not user:
                    return json_or_error("Account not found.")
                uid = int(user["id"])
                from customer_account_platform import user_can_use_personal_mode

                if not user_can_use_personal_mode(conn, uid):
                    return json_or_error("No personal profile on this contact.")
                login_email = user["email"]
                if is_synthetic_customer_email(login_email) and user["phone"]:
                    login_email = user["phone"]
                from session_remember import parse_remember_device

                finish_customer_sign_in(
                    uid,
                    email=login_email,
                    remember_device=parse_remember_device(
                        payload.get("remember_device") or request.form.get("remember_device")
                    ),
                )
                next_url = _safe_next_url(payload.get("next") or request.form.get("next"))
                session.pop("customer_verified_identity", None)
                if customer_auth_wants_json() or request.is_json:
                    return {"ok": True, "redirect": next_url, "login": True}
                return customer_auth_json_ok(next_url)

        with db() as conn:
            migrate_verification_tables(conn)
            existing = find_user_by_contact(conn, channel, target)
            signup_eligibility = evaluate_signup_contact(
                conn,
                existing,
                user_account_kind=user_account_kind,
                user_owns_store=user_owns_store,
                user_has_customer_profile=user_has_customer_profile,
                ACCOUNT_KIND_CUSTOMER=ACCOUNT_KIND_CUSTOMER,
                ACCOUNT_KIND_MERCHANT=ACCOUNT_KIND_MERCHANT,
            )
            mode = signup_eligibility.get("status", "new")
            user_id = signup_eligibility.get("user_id")
            set_verified_identity(
                session,
                channel=channel,
                target=target,
                mode=mode,
                user_id=user_id,
            )
            suggested = generate_username(conn)
        body = {
            "ok": True,
            "verified": True,
            "channel": channel,
            "target": target,
            "masked": mask_target(channel, target),
            "username": suggested,
            "mode": mode,
            "skip_password": mode in ("activate", "resume"),
        }
        if mode == "activate":
            body["lead"] = "Pick a username for personal mode. Your business password stays the same."
        return jsonify(body) if customer_auth_wants_json() or request.is_json else body

    @app.get("/account/username/check")
    def customer_username_check():
        raw = (request.args.get("q") or "").strip().lower()
        username = validate_username(raw)
        if not username:
            return {"ok": False, "available": False, "error": "Use 3–30 characters: letters, numbers, _ and ."}
        with db() as conn:
            migrate_verification_tables(conn)
            available = username_available(conn, username)
        return {"ok": True, "available": available, "username": username}

    @app.post("/account/onboarding/complete")
    def customer_onboarding_complete():
        verified = peek_verified_identity(session)
        if not verified:
            return json_or_error("Verification expired. Start again.")

        username_raw = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        display_name = (request.form.get("display_name") or "").strip() or None
        bio = (request.form.get("bio") or "").strip() or None
        next_url = _safe_next_url(request.form.get("next"))

        username = validate_username(username_raw)
        if not username:
            return json_or_error("Pick a valid username (letters, numbers, _ . — start with a letter).")

        mode = verified.get("mode", "new")
        existing_user_id = verified.get("user_id")
        activating = mode in ("activate", "resume") and existing_user_id

        if not activating:
            if len(password) < 12:
                return json_or_error("Use a password with at least 12 characters.")
            if password != confirm:
                return json_or_error("Passwords do not match.")
        elif password or confirm:
            if len(password) < 12:
                return json_or_error("Use a password with at least 12 characters.")
            if password != confirm:
                return json_or_error("Passwords do not match.")

        channel = verified["channel"]
        target = verified["target"]
        email = target if channel == "email" else phone_placeholder_email(target)
        phone = target if channel == "phone" else None

        from werkzeug.security import generate_password_hash

        from app import save_uploaded_image

        avatar_url = None
        try:
            avatar_url = save_uploaded_image("avatar")
        except ValueError as exc:
            return json_or_error(str(exc))

        try:
            with db() as conn:
                migrate_verification_tables(conn)
                if not username_available(conn, username):
                    return json_or_error("That username is taken. Try another.")

                if activating:
                    user_id = int(existing_user_id)
                    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                    if not user:
                        return json_or_error("Account not found. Start again.")
                    user_id = int(existing_user_id)
                    if password and len(password) >= 12:
                        conn.execute(
                            "UPDATE users SET password_hash = ? WHERE id = ?",
                            (
                                generate_password_hash(password, method="pbkdf2:sha256:600000"),
                                user_id,
                            ),
                        )
                    if channel == "phone" and not user["phone"]:
                        conn.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, user_id))
                    now = _now()
                    conn.execute(
                        """INSERT INTO customer_account_profiles
                           (user_id, display_name, phone, username, avatar_url, bio, linked_visitor_key, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(user_id) DO UPDATE SET
                             display_name = COALESCE(excluded.display_name, customer_account_profiles.display_name),
                             phone = COALESCE(excluded.phone, customer_account_profiles.phone),
                             username = excluded.username,
                             avatar_url = COALESCE(excluded.avatar_url, customer_account_profiles.avatar_url),
                             bio = COALESCE(excluded.bio, customer_account_profiles.bio),
                             linked_visitor_key = COALESCE(excluded.linked_visitor_key, customer_account_profiles.linked_visitor_key),
                             updated_at = excluded.updated_at""",
                        (
                            user_id,
                            display_name or username,
                            phone or user["phone"],
                            username,
                            avatar_url,
                            bio,
                            ensure_visitor_key(session),
                            now,
                        ),
                    )
                    login_email = user["email"]
                    if is_synthetic_customer_email(login_email) and (phone or user["phone"]):
                        login_email = phone or user["phone"]
                    attach_visitor_to_customer(
                        conn,
                        ensure_visitor_key(session),
                        user_id,
                        email=login_email if "@" in login_email and not is_synthetic_customer_email(login_email) else "",
                        display_name=display_name or username,
                        phone=phone or user["phone"],
                    )
                else:
                    if channel == "email":
                        dup = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
                    else:
                        dup = conn.execute(
                            "SELECT id FROM users WHERE phone = ? OR email = ?",
                            (phone, email),
                        ).fetchone()
                    if dup:
                        return json_or_error("An account already exists for this contact.")

                    cur = conn.execute(
                        """INSERT INTO users (email, password_hash, account_kind, phone)
                           VALUES (?, ?, ?, ?)""",
                        (
                            email,
                            generate_password_hash(password, method="pbkdf2:sha256:600000"),
                            ACCOUNT_KIND_CUSTOMER,
                            phone,
                        ),
                    )
                    user_id = int(cur.lastrowid)
                    now = _now()
                    conn.execute(
                        """INSERT INTO customer_account_profiles
                           (user_id, display_name, phone, username, avatar_url, bio, linked_visitor_key, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            user_id,
                            display_name or username,
                            phone,
                            username,
                            avatar_url,
                            bio,
                            ensure_visitor_key(session),
                            now,
                        ),
                    )
                    attach_visitor_to_customer(
                        conn,
                        ensure_visitor_key(session),
                        user_id,
                        email=email if channel == "email" else "",
                        display_name=display_name or username,
                        phone=phone,
                    )
            pop_verified_identity(session)
            from session_remember import parse_remember_device

            sign_in_customer(
                session,
                user_id,
                csrf_fn=csrf_token,
                remember_device=parse_remember_device(request.form.get("remember_device")),
            )
            if customer_auth_wants_json() or request.is_json:
                return {
                    "ok": True,
                    "redirect": next_url,
                    "needs_link_email": True,
                }
            from flask import flash, redirect

            flash(
                "Shopping is now active on this phone." if activating else "Welcome! Your account is ready.",
                "success",
            )
            return redirect(next_url)
        except sqlite3.IntegrityError:
            return json_or_error("Could not create account. Try a different username.")

    @app.post("/account/link-email/send")
    def customer_link_email_send():
        """Send OTP to link a real email after phone registration (customer or merchant)."""
        from customer_account_platform import current_customer_id

        payload = request.get_json(silent=True) or {}
        email = normalize_email(payload.get("email") or request.form.get("email") or "")
        if not email:
            return json_or_error("Enter a valid email address.")
        if is_synthetic_customer_email(email):
            return json_or_error("Enter a real email address.")

        uid = current_customer_id() or session.get("user_id")
        if not uid:
            return json_or_error("Sign in first.", 401)

        with db() as conn:
            migrate_verification_tables(conn)
            taken = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email, int(uid)),
            ).fetchone()
            if taken:
                return json_or_error("That email is already linked to another account.")
            ok, message, meta = send_verification_code(
                app, conn, channel="email", target=email, purpose="link_email"
            )
            if not ok:
                return json_or_error(message, 429)
            session["pending_link_email"] = email
        return jsonify({"ok": True, "message": message, **(meta or {})})

    @app.post("/account/link-email/check")
    def customer_link_email_check():
        from customer_account_platform import current_customer_id

        payload = request.get_json(silent=True) or {}
        email = normalize_email(
            payload.get("email") or session.get("pending_link_email") or ""
        )
        code = (payload.get("code") or "").strip()
        uid = current_customer_id() or session.get("user_id")
        if not uid:
            return json_or_error("Sign in first.", 401)
        if not email or not code.isdigit() or len(code) != 6:
            return json_or_error("Enter the 6-digit code.")

        with db() as conn:
            migrate_verification_tables(conn)
            ok, message = verify_code(
                conn, channel="email", target=email, code=code, purpose="link_email"
            )
            if not ok:
                return json_or_error(message)
            taken = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email, int(uid)),
            ).fetchone()
            if taken:
                return json_or_error("That email is already linked to another account.")
            conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, int(uid)))
            # Enable email as a login option once linked
            try:
                cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
                if "allow_email_login" not in cols:
                    conn.execute(
                        "ALTER TABLE users ADD COLUMN allow_email_login INTEGER NOT NULL DEFAULT 0"
                    )
            except Exception:
                rid = uuid.uuid4().hex[:12]
                app.logger.error("customer_verification_alter_failed uid=%s reference=%s", uid, rid, exc_info=True)
                return jsonify({"ok": False, "error": "schema_migration_failed", "reference": rid}), 500
            try:
                cur = conn.execute(
                    "UPDATE users SET allow_email_login = 1 WHERE id = ?", (int(uid),)
                )
                if cur.rowcount == 0:
                    rid = uuid.uuid4().hex[:12]
                    app.logger.error("customer_verification_update_0rows uid=%s reference=%s", uid, rid)
                    return jsonify({"ok": False, "error": "account_link_failed", "reference": rid}), 500
            except Exception:
                rid = uuid.uuid4().hex[:12]
                app.logger.error("customer_verification_update_failed uid=%s reference=%s", uid, rid, exc_info=True)
                return jsonify({"ok": False, "error": "account_link_failed", "reference": rid}), 500
        session.pop("pending_link_email", None)
        # Merchant vs customer redirect
        if session.get("user_id") and not current_customer_id():
            try:
                next_url = url_for("bos.store")
            except Exception:
                _log.debug("customer_verification_url_for_failed", exc_info=True, extra={"op": "customer_verification_redirect"})
                next_url = "/app/stores"
        else:
            next_url = _safe_next_url(payload.get("next"))
        return jsonify({"ok": True, "redirect": next_url, "email": email})
