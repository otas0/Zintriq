"""In-memory metrics counters for /metrics-basic (Step 2.4)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

_started_at = time.time()
_requests_total = 0
_errors_total = 0
_errors_by_type: dict[str, int] = {}
_last_error_ts: str | None = None


def increment_requests() -> None:
    global _requests_total
    _requests_total += 1


def increment_error(error_type: str) -> None:
    global _errors_total, _last_error_ts
    _errors_total += 1
    _errors_by_type[error_type] = _errors_by_type.get(error_type, 0) + 1
    _last_error_ts = datetime.now(timezone.utc).isoformat()


def get_metrics() -> dict:
    import subprocess
    try:
        version = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        version = "unknown"

    return {
        "uptime_s": int(time.time() - _started_at),
        "requests_total": _requests_total,
        "errors_total": _errors_total,
        "errors_by_type": dict(_errors_by_type),
        "last_error_ts": _last_error_ts,
        "started_at": datetime.fromtimestamp(_started_at, tz=timezone.utc).isoformat(),
        "version": version,
    }
