"""Public site color scheme: cookie preference + resolved light/dark for SSR."""

from __future__ import annotations

from flask import request

THEME_COOKIE = "theme"
THEME_COOKIE_LEGACY = "mq_theme"
RESOLVED_COOKIE = "mq_theme_resolved"
PREFS = ("system", "light", "dark")


def _cookie(name: str) -> str:
    return (request.cookies.get(name) or "").strip().lower()


def public_theme_attrs() -> dict[str, str]:
    pref = _cookie(THEME_COOKIE) or _cookie(THEME_COOKIE_LEGACY)
    if pref == "yellow":
        pref = "light"
    if pref not in PREFS:
        pref = "system"
    if pref in ("light", "dark"):
        theme = pref
    else:
        theme = ""
    return {"html_theme": theme, "html_theme_pref": pref}
