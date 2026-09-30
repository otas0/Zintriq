"""Error capture, @log_errors decorator, and global 500 handler."""

from __future__ import annotations

import logging
from functools import wraps

from observability.context import current_request_id, get_context


def capture_error(exc, *, event: str, level: str = "ERROR", **context) -> None:
    """Log an exception with structured context."""
    log = logging.getLogger("app.error")
    log.log(getattr(logging, level, logging.ERROR), event, exc_info=exc, extra=context)


def log_errors(fn):
    """Decorator: log exceptions on route handlers, then re-raise."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            from werkzeug.exceptions import HTTPException
            if isinstance(exc, HTTPException):
                if exc.code < 500:
                    logging.getLogger("app.error").warning(
                        "http_exception",
                        extra={
                            "route": get_context("route", ""),
                            "method": get_context("method", ""),
                            "request_id": current_request_id(),
                            "status": exc.code,
                        },
                    )
                else:
                    capture_error(
                        exc,
                        event="http_exception_5xx",
                        route=get_context("route", ""),
                        method=get_context("method", ""),
                        request_id=current_request_id(),
                        status=exc.code,
                    )
            else:
                capture_error(
                    exc,
                    event="route_exception",
                    route=get_context("route", ""),
                    method=get_context("method", ""),
                    request_id=current_request_id(),
                )
            raise
    return wrapper


def register_error_handlers(app) -> None:
    """Register global exception handler."""
    from flask import render_template_string, request

    ERROR_TEMPLATE = """<!doctype html>
<html><head><title>Error</title></head>
<body>
<h1>Something went wrong</h1>
<p>Please contact support with reference: <strong>{{ reference }}</strong></p>
</body></html>"""

    @app.errorhandler(Exception)
    def handle_uncaught(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e

        rid = current_request_id()
        logging.getLogger("app.error").error(
            "unhandled_exception",
            exc_info=True,
            extra={
                "route": request.path,
                "method": request.method,
                "request_id": rid,
            },
        )

        from observability.metrics import increment_error
        increment_error(type(e).__name__)

        if request.accept_mimetypes.best == "application/json":
            from flask import jsonify
            return jsonify({"error": "internal_error", "reference": rid}), 500

        return render_template_string(ERROR_TEMPLATE, reference=rid), 500
