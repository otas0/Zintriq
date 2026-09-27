"""External call tracing — context manager for outbound HTTP and DB queries."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager

_log = logging.getLogger("app.observability.trace")

_SLOW_QUERY_MS = int(os.environ.get("SLOW_QUERY_MS", "500"))


@contextmanager
def trace(name: str, **fields):
    """Trace an outbound call with duration and error tracking.
    
    Usage:
        with trace("payment.stripe.create_session", provider="stripe", op="create_session"):
            resp = urllib.request.urlopen(...)
    
    Logs:
        - trace_start at DEBUG when entering
        - trace_ok at INFO with duration_ms on success
        - trace_fail at ERROR with duration_ms and exc_info on failure
    
    Re-raises all exceptions. Never swallows.
    """
    start = time.monotonic()
    _log.debug("trace_start", extra={"trace": name, **fields})
    try:
        yield
    except Exception:
        duration = int((time.monotonic() - start) * 1000)
        _log.error("trace_fail", extra={"trace": name, "duration_ms": duration, **fields}, exc_info=True)
        raise
    else:
        duration = int((time.monotonic() - start) * 1000)
        _log.info("trace_ok", extra={"trace": name, "duration_ms": duration, **fields})


@contextmanager
def slow_query(op: str, *, threshold_ms: int | None = None):
    """Warn when a DB query exceeds the slow-query threshold.

    Usage:
        with slow_query("store_analytics_rebuild"):
            conn.execute("SELECT ...")

    Logs slow_query_warn at WARNING when duration > threshold (default 500ms,
    override via SLOW_QUERY_MS env var or threshold_ms kwarg).
    Re-raises all exceptions. Never swallows.
    """
    limit = threshold_ms if threshold_ms is not None else _SLOW_QUERY_MS
    start = time.monotonic()
    try:
        yield
    except Exception:
        duration = int((time.monotonic() - start) * 1000)
        if duration >= limit:
            _log.warning("slow_query_fail", extra={"op": op, "duration_ms": duration, "threshold_ms": limit}, exc_info=True)
        raise
    else:
        duration = int((time.monotonic() - start) * 1000)
        if duration >= limit:
            _log.warning("slow_query_warn", extra={"op": op, "duration_ms": duration, "threshold_ms": limit})
