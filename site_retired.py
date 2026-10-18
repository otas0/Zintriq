"""Return 404 for retired public website routes.

Desktop Application (ZINTRIQ_DESKTOP=1) still serves /studio, /build, and
builder-core. The public website does not host Application runtimes.
/studio/desktop and /api/studio/* stay on every mode.
"""

from __future__ import annotations

from flask import Flask, abort, request

# Second path segment under a market prefix, or the path itself.
_RETIRED_SLUGS = frozenset(
    {
        "primitives",
        "templates",
        "how-it-works",
        "compositions",
        "connections",
        "customers",
        "blog",
        "community",
        "activate",
        "extend",
    }
)

_RETIRED_EXACT = frozenset(
    {
        "/discover",
        "/venues",
        "/places",
        "/home",
        "/community",
        "/templates",
        "/activate",
        "/primitives",
        "/how-it-works",
        "/compositions",
        "/connections",
        "/customers",
        "/blog",
        "/extend",
        "/workspace",
        "/my-stores",
        "/create",
        "/manage",
        "/app",
        "/builder",
    }
)

_RETIRED_PREFIXES = (
    "/discover/",
    "/venues/",
    "/home/",
    "/activate/",
    "/compositions/",
    "/connections/",
    "/customers/",
    "/blog/",
    "/workspace/",
    "/my-stores/",
    "/manage/",
    "/create/",
)


def _norm(path: str) -> str:
    if not path:
        return "/"
    if len(path) > 1 and path.endswith("/"):
        return path[:-1]
    return path


def is_retired_web_path(path: str, *, desktop: bool) -> bool:
    path = _norm(path)
    if path.startswith("/api/"):
        if path == "/api/builder-core" or path.startswith("/api/builder-core/"):
            return not desktop
        return False
    if path == "/studio/desktop" or path.startswith("/studio/desktop/"):
        return False
    if path.startswith("/api/studio"):
        return False
    # Guest remember stays registered for the desktop auth allowlist.
    if path == "/places/remember" or path.startswith("/guest/"):
        return False
    if (
        path == "/build"
        or path.startswith("/build/")
        or path == "/builder-runtime"
        or path.startswith("/builder-runtime/")
    ):
        return not desktop
    if path == "/store" or path.startswith("/store/"):
        return False
    if path == "/place" or path.startswith("/place/"):
        return False
    if path == "/account/workspaces" or path.startswith("/account/workspaces/"):
        return not desktop
    if path == "/account" or path.startswith("/account/"):
        return False
    if path == "/app/account" or path.startswith("/app/account/"):
        return False
    # Member management is not a public-web surface.
    if path in {"/app/settings", "/app/team", "/app/workspaces"} or path.startswith("/app/settings/"):
        return False
    # Community HTML is desktop-only; web always retires /app/* below.
    if desktop and (path == "/app/community" or path.startswith("/app/community/")):
        return False

    if not desktop and (path == "/studio" or path.startswith("/studio/")):
        return True

    if path in _RETIRED_EXACT or path.startswith(_RETIRED_PREFIXES):
        return True
    if path == "/places" or (path.startswith("/places/") and path != "/places/remember"):
        return True
    if path == "/app" or path.startswith("/app/"):
        return True

    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[1] in _RETIRED_SLUGS:
        return True
    if len(parts) >= 2 and parts[1] == "blog":
        return True
    if parts and parts[0] in _RETIRED_SLUGS:
        return True
    return False


def register_retired_routes(app: Flask) -> None:
    @app.before_request
    def _retired_web_pages():
        from desktop.server_mode import desktop_enabled, remote_is_loopback, tokens_match, TOKEN_HEADER
        import os

        path = request.path or "/"
        desktop = False
        if desktop_enabled() and remote_is_loopback(request.remote_addr or ""):
            presented = request.headers.get(TOKEN_HEADER) or ""
            expected = os.environ.get("ZINTRIQ_DESKTOP_TOKEN") or ""
            desktop = tokens_match(presented, expected)
        if path.startswith("/static/builder/"):
            name = path.rsplit("/", 1)[-1]
            if not desktop or name in {
                "universal-builder.js",
                "universal-builder.css",
                "studio-graph.js",
                "universal-canvas.js",
                "experience-builder.js",
                "experience-builder.css",
                "experience-builder-responsive.css",
                "builder-preview.js",
                "project-transfer.js",
            }:
                abort(404)
        elif path.startswith("/static/studio/"):
            if not desktop:
                abort(404)
        if is_retired_web_path(path, desktop=desktop):
            abort(404)
        return None

    @app.context_processor
    def _site_flags():
        try:
            from billing_platform import billing_enabled as zintriq_billing_enabled
            from site_config import (
                BUILD_LOG,
                COMMUNITY_SHARE_PAGES,
                HARDWARE_SALES_ENABLED,
                HW_SPECS,
                HW_STAGE,
                PRICE_PERSONAL_MONTHLY_USD,
                PRICE_TEAM_SEAT_MONTHLY_USD,
                SITE_STAGE,
                STORAGE_QUOTA_PER_SEAT,
                STORAGE_QUOTA_PERSONAL,
                TRIAL_DAYS,
            )
        except ImportError:
            return {}

        return {
            "site_stage": SITE_STAGE,
            "billing_enabled": zintriq_billing_enabled(),
            "community_share_pages": COMMUNITY_SHARE_PAGES,
            "hardware_sales_enabled": HARDWARE_SALES_ENABLED,
            "price_personal": PRICE_PERSONAL_MONTHLY_USD,
            "price_team": PRICE_TEAM_SEAT_MONTHLY_USD,
            "trial_days": TRIAL_DAYS,
            "quota_personal": STORAGE_QUOTA_PERSONAL,
            "quota_seat": STORAGE_QUOTA_PER_SEAT,
            "build_log": BUILD_LOG or [],
            "hw_stage": HW_STAGE or "",
            "hw_specs": HW_SPECS or [],
        }
