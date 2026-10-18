"""Register the same customer-account view on /store and /build."""

from __future__ import annotations

from collections.abc import Callable


def work_account_route(app, suffix: str = "", *, methods=None, endpoint: str | None = None):
    methods = list(methods or ["GET"])

    def decorator(view: Callable):
        name = endpoint or view.__name__
        rest = f"/{suffix}" if suffix else ""
        app.add_url_rule(
            f"/store/<work_slug>/account{rest}",
            endpoint=name,
            view_func=view,
            methods=methods,
        )
        app.add_url_rule(
            f"/build/<work_slug>/account{rest}",
            endpoint=f"{name}_build",
            view_func=view,
            methods=methods,
        )
        return view

    return decorator
