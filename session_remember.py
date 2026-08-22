"""Session persistence — optional “Remember this device” on sign-in."""

from __future__ import annotations

from typing import Any

# Stored in the signed session so we can re-apply permanent=True on every request.
REMEMBER_SESSION_KEY = "_remember_device"
CUSTOMER_REMEMBER_COOKIE = "mq_customer_remember"
CUSTOMER_REMEMBER_MAX_AGE = 400 * 24 * 3600


def parse_remember_device(raw: Any) -> bool:
    """Return True unless the user explicitly opted out."""
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    value = str(raw).strip().lower()
    if value in {"", "0", "false", "off", "no"}:
        return False
    return True


def apply_remember_device(flask_session, remember: bool) -> None:
    remember = bool(remember)
    flask_session[REMEMBER_SESSION_KEY] = remember
    flask_session.permanent = remember
    flask_session.modified = True


def refresh_session_persistence(flask_session) -> None:
    """Keep long-lived cookies when the session dict is modified later in the request."""
    if flask_session.get(REMEMBER_SESSION_KEY):
        if not flask_session.permanent:
            flask_session.permanent = True
            flask_session.modified = True


def customer_remember_cookie_kwargs(app) -> dict[str, Any]:
    return {
        "max_age": CUSTOMER_REMEMBER_MAX_AGE,
        "httponly": True,
        "samesite": app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        "secure": bool(app.config.get("SESSION_COOKIE_SECURE", False)),
        "path": "/",
    }


def customer_remember_token(secret_key: str, user_id: int) -> str:
    from itsdangerous import URLSafeTimedSerializer

    serializer = URLSafeTimedSerializer(secret_key, salt="customer-remember-v1")
    return serializer.dumps({"uid": int(user_id)})


def customer_id_from_remember_token(secret_key: str, token: str) -> int | None:
    from itsdangerous import BadSignature, SignatureExpired
    from itsdangerous import URLSafeTimedSerializer

    serializer = URLSafeTimedSerializer(secret_key, salt="customer-remember-v1")
    try:
        data = serializer.loads(token, max_age=CUSTOMER_REMEMBER_MAX_AGE)
        return int(data["uid"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None
