"""Structured JSON logging factory and formatter."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from observability.context import get_context
from observability.filters import ContextFilter, PIIFilter

_INITIALIZED = False


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        now = datetime.fromtimestamp(record.created, tz=timezone.utc)
        data = {
            "ts": now.isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or None,
            "user_id": getattr(record, "user_id", None),
            "workspace_id": getattr(record, "workspace_id", None),
            "route": getattr(record, "route", None) or None,
            "method": getattr(record, "method", None) or None,
            "status": getattr(record, "status", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "error_type": None,
            "error_msg": None,
            "stack": None,
        }

        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            data["error_type"] = exc_type.__name__ if exc_type else None
            data["error_msg"] = str(exc_value) if exc_value else None
            data["stack"] = "".join(traceback.format_exception(*record.exc_info))

        for key in ("status", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                data[key] = val

        extra_keys = set(record.__dict__.keys()) - set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())
        safe_extra = extra_keys - {
            "request_id", "user_id", "workspace_id", "route", "method",
            "status", "duration_ms", "stack",
        }
        for key in safe_extra:
            if key not in data:
                data[key] = getattr(record, key)

        return json.dumps(data, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    """Dev-friendly human-readable format."""

    def format(self, record: logging.LogRecord) -> str:
        now = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts = now.strftime("%H:%M:%S")
        rid = getattr(record, "request_id", "") or ""
        rid_part = f" [{rid[:8]}]" if rid else ""
        msg = record.getMessage()
        line = f"{ts} {record.levelname:<5} {record.name}{rid_part} {msg}"
        if record.exc_info:
            line += "\n" + "".join(traceback.format_exception(*record.exc_info))
        return line


def init_logging(*, app=None) -> None:
    """Configure root logger ONCE. Idempotent."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    env = os.environ.get("ENV", os.environ.get("FLASK_ENV", "development"))
    is_prod = env.lower() in ("production", "prod")
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    ctx_filter = ContextFilter()
    pii_filter = PIIFilter()

    if is_prod:
        json_fmt = JSONFormatter()
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(json_fmt)
        console_handler.addFilter(ctx_filter)
        console_handler.addFilter(pii_filter)
        root.addHandler(console_handler)

        log_dir = os.environ.get("LOG_DIR", "logs")
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=100 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(json_fmt)
        file_handler.addFilter(ctx_filter)
        file_handler.addFilter(pii_filter)
        root.addHandler(file_handler)
    else:
        human_fmt = HumanFormatter()
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(human_fmt)
        console_handler.addFilter(ctx_filter)
        console_handler.addFilter(pii_filter)
        root.addHandler(console_handler)

    logging.captureWarnings(True)
