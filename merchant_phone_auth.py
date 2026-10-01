"""Phone-first merchant (owner) auth — signup/login via SMS OTP."""

from __future__ import annotations

import sqlite3

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import generate_password_hash

from customer_verification import (
    find_user_by_contact,
    find_user_by_login,
    mask_target,
    migrate_verification_tables,
    normalize_phone,
    peek_verified_identity,
    phone_placeholder_email,
    pop_verified_identity,
    send_verification_code,
    set_verified_identity,
    verify_code,
)


def register_merchant_phone_auth(app, *, db, sign_in_user):
    def _json_error(message: str, status: int = 400):
        return jsonify({"ok": False, "error": message}), status

    @app.post("/auth/phone/send")
    def merchant_phone_send():
        data = request.get_json(silent=True) or {}
        audience = (data.get("audience") or "merchant").strip().lower()
        if audience != "merchant":
            return _json_error("Invalid audience.")
        purpose = (data.get("purpose") or "login").strip().lower()
        if purpose not in ("signup", "login"):
            purpose = "login"
        phone = normalize_phone(data.get("phone") or "")
        if not phone:
            return _json_error(
                "Enter a valid phone number with country code (e.g. +60123456789)."
            )

        if purpose == "signup":
            consent = data.get("legal_consent")
            if not consent or str(consent).lower() in ("0", "false", "no", "off"):
                return _json_error(
                    "Please accept the Terms of Service and Privacy Policy to continue."
                )

        with db() as conn:
            migrate_verification_tables(conn)
            existing = find_user_by_contact(conn, "phone", phone)
            if purpose == "signup" and existing:
                from customer_account_platform import ACCOUNT_KIND_CUSTOMER, user_account_kind

                if user_account_kind(existing) == ACCOUNT_KIND_CUSTOMER:
                    return _json_error(
                        "This phone is registered for shopping. Use a different number for business."
                    )
                return _json_error("An account already exists for this phone. Sign in instead.")
            if purpose == "login":
                if not existing:
                    return _json_error("No business account found for this phone.")
                from customer_account_platform import ACCOUNT_KIND_CUSTOMER, user_account_kind

                if user_account_kind(existing) == ACCOUNT_KIND_CUSTOMER:
                    return _json_error("This phone is a personal account. Use shopper sign-in.")

            ok, message, meta = send_verification_code(
                app, conn, channel="phone", target=phone, purpose=purpose
            )
            if not ok:
                return _json_error(message, 429)
        return jsonify({"ok": True, "message": message, **(meta or {})})

    @app.post("/auth/phone/check")
    def merchant_phone_check():
        data = request.get_json(silent=True) or {}
        audience = (data.get("audience") or "merchant").strip().lower()
        if audience != "merchant":
            return _json_error("Invalid audience.")
        purpose = (data.get("purpose") or "login").strip().lower()
        phone = normalize_phone(data.get("phone") or "")
        code = (data.get("code") or "").strip()
        if not phone or not code.isdigit() or len(code) != 6:
            return _json_error("Enter the 6-digit code.")

        with db() as conn:
            migrate_verification_tables(conn)
            ok, message = verify_code(
                conn, channel="phone", target=phone, code=code, purpose=purpose
            )
            if not ok:
                return _json_error(message)

            if purpose == "login":
                user = find_user_by_login(conn, phone)
                if not user:
                    return _json_error("Account not found.")
                from customer_account_platform import ACCOUNT_KIND_CUSTOMER, user_account_kind
                from session_remember import parse_remember_device

                if user_account_kind(user) == ACCOUNT_KIND_CUSTOMER:
                    return _json_error("This phone is a personal account.")
                if user["two_factor_secret"]:
                    session["pending_2fa_user_id"] = user["id"]
                    session["pending_remember_device"] = parse_remember_device(
                        data.get("remember_device")
                    )
                    return jsonify({"ok": True, "redirect": url_for("two_factor_login")})
                sign_in_user(
                    user["id"],
                    remember_device=parse_remember_device(data.get("remember_device")),
                )
                return jsonify({"ok": True, "redirect": url_for("universal_builder_home")})

            set_verified_identity(session, channel="phone", target=phone, mode="new")
            session["merchant_phone_signup"] = True
            return jsonify({
                "ok": True,
                "verified": True,
                "masked": mask_target("phone", phone),
            })

    @app.post("/auth/phone/complete")
    def merchant_phone_complete():
        if not session.get("merchant_phone_signup"):
            return _json_error("Verification expired. Start again.")
        verified = peek_verified_identity(session)
        if not verified or verified.get("channel") != "phone":
            return _json_error("Verification expired. Start again.")

        data = request.get_json(silent=True) or {}
        password = data.get("password") or ""
        confirm = data.get("confirm_password") or ""
        if len(password) < 12:
            return _json_error("Use a password with at least 12 characters.")
        if password != confirm:
            return _json_error("Passwords do not match.")

        phone = verified["target"]
        email = phone_placeholder_email(phone)

        try:
            with db() as conn:
                migrate_verification_tables(conn)
                dup = find_user_by_contact(conn, "phone", phone)
                if dup:
                    return _json_error("An account already exists for this phone.")
                cur = conn.execute(
                    """INSERT INTO users (email, password_hash, account_kind, phone)
                       VALUES (?, ?, ?, ?)""",
                    (
                        email,
                        generate_password_hash(password, method="pbkdf2:sha256:600000"),
                        "merchant",
                        phone,
                    ),
                )
                user_id = int(cur.lastrowid)
            pop_verified_identity(session)
            session.pop("merchant_phone_signup", None)
            from session_remember import parse_remember_device

            sign_in_user(
                user_id,
                remember_device=parse_remember_device(data.get("remember_device")),
            )
            return jsonify({
                "ok": True,
                "redirect": url_for("universal_builder_home"),
                "needs_link_email": True,
            })
        except sqlite3.IntegrityError:
            return _json_error("Could not create account. Try again.")

    @app.before_request
    def _block_email_register_post():
        if request.endpoint != "register" or request.method != "POST":
            return None
        if request.is_json:
            return None
        from flask import flash

        flash("Register with your phone number — email can be linked after signup.", "error")
        return redirect(url_for("register"))
