"""Request-scoped context variables for observability."""

from __future__ import annotations

import time
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_workspace_id: ContextVar[str | None] = ContextVar("workspace_id", default=None)
_route: ContextVar[str] = ContextVar("route", default="")
_method: ContextVar[str] = ContextVar("method", default="")
_start_time: ContextVar[float] = ContextVar("start_time", default=0.0)


def set_context(**kwargs) -> None:
    for key, value in kwargs.items():
        var = _CONTEXT_VARS.get(key)
        if var is not None:
            var.set(value)


def get_context(key: str, default=None):
    var = _CONTEXT_VARS.get(key)
    if var is None:
        return default
    return var.get()


def clear_context() -> None:
    _request_id.set("")
    _user_id.set(None)
    _workspace_id.set(None)
    _route.set("")
    _method.set("")
    _start_time.set(0.0)


def current_request_id() -> str:
    return _request_id.get()


_CONTEXT_VARS = {
    "request_id": _request_id,
    "user_id": _user_id,
    "workspace_id": _workspace_id,
    "route": _route,
    "method": _method,
    "start_time": _start_time,
}
