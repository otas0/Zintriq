"""Logging filters: PIIFilter (scrub secrets) and ContextFilter (inject request context)."""

from __future__ import annotations

import logging
import re

from observability.context import get_context


def _scrub(text: str) -> str:
    for pattern, replacement in PIIFilter.PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _scrub_args(args) -> tuple | dict | None:
    if isinstance(args, tuple):
        return tuple(_scrub(str(a)) if isinstance(a, str) else a for a in args)
    if isinstance(args, dict):
        return {k: _scrub(str(v)) if isinstance(v, str) else v for k, v in args.items()}
    return args


class PIIFilter(logging.Filter):
    """Scrub PII from log records. Last line of defense — must never raise."""

    PATTERNS = [
        (re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b'), '[email]'),
        (re.compile(r'\b\d{13,19}\b'), '[card_like]'),
        (re.compile(r'\b(sk|pk|rk)_(live|test)_\w+\b'), '[stripe_key]'),
        (re.compile(r'\b\+?\d[\d\s\-()]{7,}\b'), '[phone]'),
        (re.compile(r'(?i)(password|token|secret|authorization)["\']?\s*[:=]\s*\S+'), r'\1=[redacted]'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = _scrub(str(record.msg))
            if record.args:
                record.args = _scrub_args(record.args)
            if getattr(record, 'stack', None):
                record.stack = _scrub(record.stack)
        except Exception:
            pass
        return True


class ContextFilter(logging.Filter):
    """Inject request context vars into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_context("request_id", "")
        record.user_id = get_context("user_id")
        record.workspace_id = get_context("workspace_id")
        record.route = get_context("route", "")
        record.method = get_context("method", "")
        return True
