"""Pluggable invoke rate limiting.

Desktop uses the in-process backend. Cloud deployments with more than one
worker process must replace `get_rate_limiter()` with a shared store
(Redis, etc.); the in-process counters are not process-safe across workers.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Protocol

from builder_kernel.limits import (
    PUBLIC_INVOKE_HOUR_LIMIT,
    PUBLIC_INVOKE_HOUR_WINDOW,
    PUBLIC_INVOKE_MINUTE_LIMIT,
    PUBLIC_INVOKE_MINUTE_WINDOW,
)


class RateLimiter(Protocol):
    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        """Return True when the event is within the limit."""


class InProcessRateLimiter:
    """Process-local sliding windows. Suitable for single-process desktop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - float(window_seconds)
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= int(limit):
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_DEFAULT = InProcessRateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Return the active limiter. Replace this function in cloud multi-worker setups."""
    return _DEFAULT


def anonymous_write_allowed(limiter: RateLimiter, *, ip: str, project_id: int) -> bool:
    base = f"anon-write:{ip}:{int(project_id)}"
    if not limiter.allow(base + ":m", limit=PUBLIC_INVOKE_MINUTE_LIMIT, window_seconds=PUBLIC_INVOKE_MINUTE_WINDOW):
        return False
    if not limiter.allow(base + ":h", limit=PUBLIC_INVOKE_HOUR_LIMIT, window_seconds=PUBLIC_INVOKE_HOUR_WINDOW):
        return False
    return True
