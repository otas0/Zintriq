"""Creator-only login extras: new-device SMS, forgot-password, account email/phone."""

from __future__ import annotations

import sqlite3

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from customer_account_platform import ACCOUNT_KIND_CUSTOMER, user_account_kind
from customer_verification import (
    find_user_by_contact,
    find_user_by_login,
    is_synthetic_customer_email,
    migrate_verification_tables,
    normalize_email,
    normalize_phone,
    send_verification_code,
    verify_code,
)
from login_lockout import clear_login_failures, lockout_status, record_login_failure
from password_policy import hash_password, password_issues, password_needs_rehash, verify_password
from trusted_devices import (
    COOKIE_NAME,
    cookie_kwargs,
    find_trusted_device,
    issue_trusted_device,
    migrate_trusted_devices,
    revoke_user_devices,
    bump_session_version,
    user_agent_label,
)

GENERIC_LOGIN_ERROR = "Phone or password is incorrect."
FORGOT_NEUTRAL = "If that account exists, we sent a reset message."


def _client_ip() -> str:
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()


def migrate_creator_auth(conn) -> None:
    migrate_verification_tables(conn)
    migrate_trusted_devices(conn)
    from login_lockout import migrate_lockouts

    migrate_lockouts(conn)


def session_version_ok(conn, user_id: int) -> bool:
    row = conn.execute("SELECT session_version FROM users WHERE id = ?", (int(user_id),)).fetchone()
    stored = int((row["session_version"] if row else 1) or 1)
    return int(session.get("session_version") or stored) == stored


def attach_session_version(conn, user_id: int) -> None:
    try:
        row = conn.execute("SELECT session_version FROM users WHERE id = ?", (int(user_id),)).fetchone()
    except Exception:
        return
    session["session_version"] = int((row["session_version"] if row else 1) or 1)


def invalidate_sessions(conn, user_id: int) -> None:
    bump_session_version(conn, user_id)
    revoke_user_devices(conn, user_id)
    from desktop_account import revoke_all_desktop_sessions

    revoke_all_desktop_sessions(conn, user_id)


def _maybe_rehash(conn, user, password: str) -> None:
    if password_needs_rehash(user["password_hash"]):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user["id"]),
        )


def set_trusted_device_cookie(app, response, conn, user_id: int):
    token = issue_trusted_device(conn, user_id, label=user_agent_label())
    response.set_cookie(COOKIE_NAME, token, **cookie_kwargs(app))
    return response


def complete_creator_login(app, *, db, sign_in_user, user, remember: bool, issue_device: bool):
    from auth_redirects import creator_home_url, safe_creator_next
    from session_remember import parse_remember_device

    remember = parse_remember_device(remember)
    if user["two_factor_secret"] and not session.get("pending_2fa_user_id"):
        session["pending_2fa_user_id"] = user["id"]
        session["pending_remember_device"] = remember
        session["pending_issue_device"] = bool(issue_device)
        session.pop("pending_device_user_id", None)
        return redirect(url_for("two_factor_login"))

    sign_in_user(user["id"], remember_device=remember)
    with db() as conn:
        attach_session_version(conn, user["id"])
        nxt = safe_creator_next(
            request.form.get("next")
            or request.args.get("next")
            or session.pop("pending_login_next", "")
        )
        dest = nxt or creator_home_url()
        resp = redirect(dest)
        if issue_device:
            set_trusted_device_cookie(app, resp, conn, user["id"])
        return resp


def handle_creator_login(app, *, db, sign_in_user, current_user):
    from auth_redirects import creator_home_url, safe_creator_next
    from session_remember import parse_remember_device
    if current_user():
        return redirect(creator_home_url())

    pending_device = session.get("pending_device_user_id")
    if request.method != "POST":
        return render_template(
            "login.html",
            auth_next=safe_creator_next(request.args.get("next")),
            pending_package=request.args.get("package"),
            device_step=bool(pending_device),
            device_phone=session.get("pending_device_phone") or "",
            lockout_minutes=15,
        )

    from turnstile_protect import FAIL_MESSAGE, request_passes_turnstile, turnstile_configured

    identifier = (request.form.get("email") or request.form.get("identifier") or "").strip()
    password = request.form.get("password") or ""
    ip = _client_ip()

    with db() as conn:
        migrate_creator_auth(conn)
        status = lockout_status(conn, identifier, ip)
        if status["locked"]:
            flash("Too many attempts. Try again in 15 minutes.", "error")
            return render_template(
                "login.html",
                auth_next=safe_creator_next(request.form.get("next")),
                pending_package=request.form.get("package"),
                device_step=False,
                lockout_minutes=15,
            )
        if (turnstile_configured() or status["need_turnstile"]) and not request_passes_turnstile():
            flash(FAIL_MESSAGE, "error")
            return render_template(
                "login.html",
                auth_next=safe_creator_next(request.form.get("next")),
                pending_package=request.form.get("package"),
                device_step=False,
                need_turnstile=True,
                lockout_minutes=15,
            )

        user = find_user_by_login(conn, identifier)
        if (
            not user
            or not verify_password(user["password_hash"], password)
            or user_account_kind(user) == ACCOUNT_KIND_CUSTOMER
        ):
            record_login_failure(conn, identifier, ip)
            flash(GENERIC_LOGIN_ERROR, "error")
            return render_template(
                "login.html",
                auth_next=safe_creator_next(request.form.get("next")),
                pending_package=request.form.get("package"),
                device_step=False,
                lockout_minutes=15,
            )

        clear_login_failures(conn, identifier, ip)
        _maybe_rehash(conn, user, password)

        phone = (user["phone"] if "phone" in user.keys() else None) or ""
        trusted = find_trusted_device(conn, user["id"], request.cookies.get(COOKIE_NAME))
        remember = parse_remember_device(request.form.get("remember_device"))

        if phone and not trusted:
            ok, message, _meta = send_verification_code(
                app, conn, channel="phone", target=phone, purpose="login_device"
            )
            if not ok:
                flash(message, "error")
                return render_template(
                    "login.html",
                    auth_next=safe_creator_next(request.form.get("next")),
                    pending_package=request.form.get("package"),
                    device_step=False,
                    lockout_minutes=15,
                )
            session["pending_device_user_id"] = user["id"]
            session["pending_device_phone"] = phone
            session["pending_remember_device"] = remember
            session["pending_login_next"] = request.form.get("next") or ""
            flash("We sent a code to this device.", "info")
            return render_template(
                "login.html",
                auth_next=safe_creator_next(request.form.get("next")),
                pending_package=request.form.get("package"),
                device_step=True,
                device_phone=phone,
                lockout_minutes=15,
            )

        return complete_creator_login(
            app,
            db=db,
            sign_in_user=sign_in_user,
            user=user,
            remember=remember,
            issue_device=False,
        )


def register_creator_auth(app, *, db, sign_in_user, login_required, current_user, create_auth_token):
    @app.post("/login/device")
    def login_device():
        user_id = session.get("pending_device_user_id")
        phone = session.get("pending_device_phone") or ""
        code = (request.form.get("device_code") or request.form.get("code") or "").strip()
        if not user_id or not phone:
            flash(GENERIC_LOGIN_ERROR, "error")
            return redirect(url_for("login"))
        with db() as conn:
            migrate_creator_auth(conn)
            ok, message = verify_code(
                conn, channel="phone", target=phone, code=code, purpose="login_device"
            )
            if not ok:
                flash(message, "error")
                return render_template(
                    "login.html",
                    device_step=True,
                    device_phone=phone,
                    auth_next=session.get("pending_login_next") or "",
                    lockout_minutes=15,
                )
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            session.pop("pending_device_user_id", None)
            return redirect(url_for("login"))
        remember = session.pop("pending_remember_device", True)
        session.pop("pending_device_user_id", None)
        session.pop("pending_device_phone", None)
        return complete_creator_login(
            app,
            db=db,
            sign_in_user=sign_in_user,
            user=user,
            remember=remember,
            issue_device=True,
        )

    @app.post("/forgot-password/verify")
    def forgot_password_verify():
        phone = normalize_phone(request.form.get("phone") or "")
        code = (request.form.get("code") or "").strip()
        if not phone or not code:
            flash(FORGOT_NEUTRAL, "success")
            return redirect(url_for("forgot_password"))
        with db() as conn:
            migrate_creator_auth(conn)
            ok, _message = verify_code(
                conn, channel="phone", target=phone, code=code, purpose="reset"
            )
            if not ok:
                flash("That code is not valid.", "error")
                return redirect(url_for("forgot_password"))
            user = find_user_by_contact(conn, "phone", phone)
            if not user or user_account_kind(user) == ACCOUNT_KIND_CUSTOMER:
                flash(FORGOT_NEUTRAL, "success")
                return redirect(url_for("forgot_password"))
            token = create_auth_token(user["id"], "reset")
        return redirect(url_for("reset_password", token=token))

    @app.post("/account/link-email/send")
    @login_required
    def account_link_email_send():
        user = current_user()
        email = normalize_email(request.form.get("email") or (request.get_json(silent=True) or {}).get("email") or "")
        if not email or is_synthetic_customer_email(email):
            msg = "Enter a valid email address."
            if request.is_json:
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg, "error")
            return redirect(url_for("account"))
        with db() as conn:
            migrate_creator_auth(conn)
            taken = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email, user["id"]),
            ).fetchone()
            if taken:
                msg = "That email is already being used by another account."
                if request.is_json:
                    return jsonify({"ok": False, "error": msg}), 400
                flash(msg, "error")
                return redirect(url_for("account"))
            ok, message, _meta = send_verification_code(
                app, conn, channel="email", target=email, purpose="link_email"
            )
        if request.is_json:
            return jsonify({"ok": ok, "error": None if ok else message, "message": message}), (200 if ok else 429)
        flash(message if ok else message, "success" if ok else "error")
        session["pending_link_email"] = email
        return redirect(url_for("account", prompt="email"))

    @app.post("/account/link-email/check")
    @login_required
    def account_link_email_check():
        user = current_user()
        data = request.get_json(silent=True) or {}
        email = normalize_email(
            request.form.get("email") or data.get("email") or session.get("pending_link_email") or ""
        )
        code = (request.form.get("code") or data.get("code") or "").strip()
        if not email or not code:
            msg = "Enter the code we sent."
            if request.is_json:
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg, "error")
            return redirect(url_for("account"))
        with db() as conn:
            migrate_creator_auth(conn)
            ok, message = verify_code(
                conn, channel="email", target=email, code=code, purpose="link_email"
            )
            if not ok:
                if request.is_json:
                    return jsonify({"ok": False, "error": message}), 400
                flash(message, "error")
                return redirect(url_for("account"))
            try:
                conn.execute(
                    "UPDATE users SET email = ?, email_verified_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (email, user["id"]),
                )
            except sqlite3.IntegrityError:
                msg = "That email is already being used by another account."
                if request.is_json:
                    return jsonify({"ok": False, "error": msg}), 400
                flash(msg, "error")
                return redirect(url_for("account"))
        session.pop("pending_link_email", None)
        if request.is_json:
            return jsonify({"ok": True})
        flash("Email added. You can use it to sign in.", "success")
        return redirect(url_for("account"))

    @app.post("/account/change-phone/send")
    @login_required
    def account_change_phone_send():
        user = current_user()
        data = request.get_json(silent=True) or {}
        password = request.form.get("password") or data.get("password") or ""
        phone = normalize_phone(request.form.get("phone") or data.get("phone") or "")
        with db() as conn:
            migrate_creator_auth(conn)
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
            if not verify_password(row["password_hash"], password):
                msg = "Your password was incorrect."
                if request.is_json:
                    return jsonify({"ok": False, "error": msg}), 400
                flash(msg, "error")
                return redirect(url_for("account"))
            if not phone:
                msg = "Enter a valid phone number with country code."
                if request.is_json:
                    return jsonify({"ok": False, "error": msg}), 400
                flash(msg, "error")
                return redirect(url_for("account"))
            taken = find_user_by_contact(conn, "phone", phone)
            if taken and int(taken["id"]) != int(user["id"]):
                msg = "This number is already registered."
                if request.is_json:
                    return jsonify({"ok": False, "error": msg}), 400
                flash(msg, "error")
                return redirect(url_for("account"))
            ok, message, _meta = send_verification_code(
                app, conn, channel="phone", target=phone, purpose="change_phone"
            )
        session["pending_change_phone"] = phone
        if request.is_json:
            return jsonify({"ok": ok, "message": message, "error": None if ok else message}), (200 if ok else 429)
        flash(message, "success" if ok else "error")
        return redirect(url_for("account"))

    @app.post("/account/change-phone/check")
    @login_required
    def account_change_phone_check():
        user = current_user()
        data = request.get_json(silent=True) or {}
        phone = normalize_phone(
            request.form.get("phone") or data.get("phone") or session.get("pending_change_phone") or ""
        )
        code = (request.form.get("code") or data.get("code") or "").strip()
        with db() as conn:
            migrate_creator_auth(conn)
            ok, message = verify_code(
                conn, channel="phone", target=phone, code=code, purpose="change_phone"
            )
            if not ok:
                if request.is_json:
                    return jsonify({"ok": False, "error": message}), 400
                flash(message, "error")
                return redirect(url_for("account"))
            old = conn.execute("SELECT phone FROM users WHERE id = ?", (user["id"],)).fetchone()
            conn.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, user["id"]))
            old_phone = old["phone"] if old else None
            if old_phone and old_phone != phone:
                try:
                    from customer_verification import deliver_otp

                    deliver_otp(app, channel="phone", target=old_phone, code="000000")
                except Exception:
                    pass
        session.pop("pending_change_phone", None)
        if request.is_json:
            return jsonify({"ok": True})
        flash("Phone number updated.", "success")
        return redirect(url_for("account"))

    @app.route("/account/verify-phone", methods=["GET", "POST"])
    @login_required
    def account_verify_phone():
        user = current_user()
        with db() as conn:
            row = conn.execute("SELECT phone FROM users WHERE id = ?", (user["id"],)).fetchone()
        if row and row["phone"]:
            return redirect(url_for("account"))
        if request.method == "POST":
            action = request.form.get("action") or "send"
            phone = normalize_phone(request.form.get("phone") or session.get("pending_force_phone") or "")
            if action == "check":
                code = (request.form.get("code") or "").strip()
                with db() as conn:
                    ok, message = verify_code(
                        conn, channel="phone", target=phone, code=code, purpose="force_phone"
                    )
                    if not ok:
                        flash(message, "error")
                        return render_template("verify_phone.html", phone=phone)
                    taken = find_user_by_contact(conn, "phone", phone)
                    if taken and int(taken["id"]) != int(user["id"]):
                        flash("This number is already registered.", "error")
                        return render_template("verify_phone.html", phone=phone)
                    conn.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, user["id"]))
                session.pop("pending_force_phone", None)
                flash("Phone number saved.", "success")
                return redirect(url_for("account"))
            if not phone:
                flash("Enter a valid phone number with country code.", "error")
                return render_template("verify_phone.html", phone="")
            with db() as conn:
                taken = find_user_by_contact(conn, "phone", phone)
                if taken and int(taken["id"]) != int(user["id"]):
                    flash("This number is already registered.", "error")
                    return render_template("verify_phone.html", phone=phone)
                ok, message, _meta = send_verification_code(
                    app, conn, channel="phone", target=phone, purpose="force_phone"
                )
            session["pending_force_phone"] = phone
            flash(message, "success" if ok else "error")
            return render_template("verify_phone.html", phone=phone, code_sent=ok)
        return render_template("verify_phone.html", phone=session.get("pending_force_phone") or "")

    @app.before_request
    def require_creator_phone():
        # Forced bind is off until SMS delivery is live (Twilio). Email accounts
        # without a phone must still reach the portal.
        return None
