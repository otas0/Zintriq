"""Desktop connector whitelist. Unknown schemes are refused."""

from __future__ import annotations

from urllib.parse import urlparse

ALLOWED = frozenset({"http", "https", "ws", "wss", "serial", "mqtt"})


class ConnectorError(ValueError):
    pass


def allow(url: str) -> str:
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED:
        raise ConnectorError(f"connector not allowed: {scheme or 'none'}")
    if scheme in {"http", "https", "ws", "wss"} and parsed.hostname not in {"127.0.0.1", "localhost"}:
        # Remote HTTP is allowed on the whitelist; callers still go through zintriq.http.
        pass
    return raw
