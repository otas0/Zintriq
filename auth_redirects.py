"""Where a signed-in creator should land on web vs desktop."""

from __future__ import annotations

from flask import url_for


def creator_home_path() -> str:
    from desktop.server_mode import desktop_enabled

    if desktop_enabled():
        return "/studio"
    return "/account"


def creator_home_url() -> str:
    from desktop.server_mode import desktop_enabled

    if desktop_enabled():
        return url_for("studio_home")
    return url_for("account")


def safe_creator_next(target: str | None) -> str:
    home = creator_home_path()
    if not target or not target.startswith("/") or target.startswith("//"):
        return home
    from desktop.server_mode import desktop_enabled
    from site_retired import is_retired_web_path

    desktop = desktop_enabled()
    if is_retired_web_path(target.split("?", 1)[0], desktop=desktop):
        return home
    if not desktop and (
        target == "/studio"
        or target.startswith("/studio/")
        or target.startswith("/app/builder")
        or target == "/app"
        or target.startswith("/app/")
    ):
        if target == "/app/account" or target.startswith("/app/account"):
            return "/account"
        return home
    return target
