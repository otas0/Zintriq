"""Supported languages + runtime UI translation for MarketQR / Zintriq."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import g, has_app_context, request, session

_log = logging.getLogger("app.i18n")

# BCP 47 codes. Swedish is `sv` (not `se` — that is Northern Sami).
SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "name": "English", "native": "English", "dir": "ltr"},
    {"code": "zh-Hans", "name": "Chinese (Simplified)", "native": "简体中文", "dir": "ltr"},
    {"code": "zh-Hant", "name": "Chinese (Traditional)", "native": "繁體中文", "dir": "ltr"},
    {"code": "ja", "name": "Japanese", "native": "日本語", "dir": "ltr"},
    {"code": "ms", "name": "Malay", "native": "Bahasa Melayu", "dir": "ltr"},
    {"code": "id", "name": "Indonesian", "native": "Bahasa Indonesia", "dir": "ltr"},
    {"code": "ko", "name": "Korean", "native": "한국어", "dir": "ltr"},
    {"code": "th", "name": "Thai", "native": "ไทย", "dir": "ltr"},
    {"code": "vi", "name": "Vietnamese", "native": "Tiếng Việt", "dir": "ltr"},
    {"code": "fil", "name": "Filipino", "native": "Filipino", "dir": "ltr"},
    {"code": "es", "name": "Spanish", "native": "Español", "dir": "ltr"},
    {"code": "pt-BR", "name": "Portuguese (Brazil)", "native": "Português (Brasil)", "dir": "ltr"},
    {"code": "fr", "name": "French", "native": "Français", "dir": "ltr"},
    {"code": "de", "name": "German", "native": "Deutsch", "dir": "ltr"},
    {"code": "ar", "name": "Arabic", "native": "العربية", "dir": "rtl"},
    {"code": "sv", "name": "Swedish", "native": "Svenska", "dir": "ltr"},
]

DEFAULT_LANGUAGE = "en"
LANG_SESSION_KEY = "ui_lang"
LANG_COOKIE = "mq_lang"
_LOCALES_DIR = Path(__file__).resolve().parent / "i18n" / "locales"

_ALIASES = {
    "zh": "zh-Hans",
    "zh-cn": "zh-Hans",
    "zh-sg": "zh-Hans",
    "zh-tw": "zh-Hant",
    "zh-hk": "zh-Hant",
    "pt": "pt-BR",
    "tl": "fil",
    "se": "sv",
}


def supported_language_codes() -> set[str]:
    return {item["code"] for item in SUPPORTED_LANGUAGES}


def language_meta(code: str) -> dict[str, str]:
    code = normalize_language(code)
    for item in SUPPORTED_LANGUAGES:
        if item["code"] == code:
            return dict(item)
    return dict(SUPPORTED_LANGUAGES[0])


def normalize_language(value: Any, *, default: str = DEFAULT_LANGUAGE) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    key = raw.replace("_", "-")
    lower = key.lower()
    codes = supported_language_codes()
    for code in codes:
        if code.lower() == lower:
            return code
    mapped = _ALIASES.get(lower)
    if mapped and mapped in codes:
        return mapped
    primary = lower.split("-", 1)[0]
    for code in codes:
        if code.lower() == primary:
            return code
    return default


def language_options() -> list[dict[str, str]]:
    return [dict(item) for item in SUPPORTED_LANGUAGES]


@lru_cache(maxsize=32)
def _load_locale(code: str) -> dict[str, str]:
    code = normalize_language(code)
    path = _LOCALES_DIR / f"{code}.json"
    if not path.exists():
        path = _LOCALES_DIR / f"{DEFAULT_LANGUAGE}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _log.debug("locale_file_load_failed", exc_info=True, extra={"op": "_load_locale"})
        return {}
    return {str(k): str(v) for k, v in data.items()}


def translate(key: str, lang: str | None = None, **vars: Any) -> str:
    """Translate a message key for the active (or given) language."""
    code = normalize_language(lang or get_active_language())
    catalog = _load_locale(code)
    text = catalog.get(key)
    if text is None:
        text = _load_locale(DEFAULT_LANGUAGE).get(key, key)
    if vars:
        try:
            text = text.format(**{k: vars[k] for k in vars})
        except (KeyError, ValueError):
            _log.debug("translate_format_failed", exc_info=True, extra={"op": "translate"})
            pass
    return text


def get_active_language() -> str:
    if has_app_context() and hasattr(g, "ui_lang") and g.ui_lang:
        return normalize_language(g.ui_lang)
    return DEFAULT_LANGUAGE


def set_active_language(code: str) -> str:
    """Persist language on the session (caller should also set cookie on response)."""
    code = normalize_language(code)
    session[LANG_SESSION_KEY] = code
    session.modified = True
    g.ui_lang = code
    return code


def resolve_request_language() -> str:
    """Priority: explicit session → cookie → browser Accept-Language → en."""
    raw = session.get(LANG_SESSION_KEY)
    if raw:
        return normalize_language(raw)
    cookie = request.cookies.get(LANG_COOKIE)
    if cookie:
        return normalize_language(cookie)

    codes = supported_language_codes()
    for item, _quality in request.accept_languages:
        key = str(item or "").strip().replace("_", "-")
        if not key:
            continue
        lower = key.lower()
        for code in codes:
            if code.lower() == lower:
                return code
        mapped = _ALIASES.get(lower)
        if mapped and mapped in codes:
            return mapped
        primary = lower.split("-", 1)[0]
        # Prefer Hans for generic Chinese from browsers (zh, zh-CN, zh-SG)
        if primary == "zh":
            if "tw" in lower or "hk" in lower or "hant" in lower:
                return "zh-Hant" if "zh-Hant" in codes else DEFAULT_LANGUAGE
            return "zh-Hans" if "zh-Hans" in codes else DEFAULT_LANGUAGE
        for code in codes:
            if code.lower() == primary or code.lower().startswith(primary + "-"):
                return code
    return DEFAULT_LANGUAGE


def register_i18n_platform(app) -> None:
    from flask import jsonify, make_response, redirect, request as flask_request

    @app.before_request
    def _i18n_before_request():
        g.ui_lang = resolve_request_language()
        g.ui_lang_dir = language_meta(g.ui_lang).get("dir", "ltr")

    @app.context_processor
    def inject_i18n():
        lang = get_active_language()
        meta = language_meta(lang)

        def _(key: str, **vars: Any) -> str:
            return translate(key, lang, **vars)

        return {
            "_": _,
            "t": _,
            "ui_lang": lang,
            "ui_lang_dir": meta.get("dir", "ltr"),
            "ui_languages": language_options(),
            "html_lang": lang,
        }

    @app.get("/api/languages")
    def api_languages():
        return jsonify({
            "languages": language_options(),
            "default": DEFAULT_LANGUAGE,
            "active": get_active_language(),
        })

    @app.post("/api/locale")
    def api_set_locale():
        data = flask_request.get_json(silent=True) or {}
        code = normalize_language(
            data.get("language") or flask_request.form.get("language")
        )
        set_active_language(code)
        resp = make_response(jsonify({
            "ok": True,
            "language": code,
            "dir": language_meta(code).get("dir", "ltr"),
            "message": translate("lang.apply", code),
        }))
        resp.set_cookie(
            LANG_COOKIE,
            code,
            max_age=60 * 60 * 24 * 365,
            samesite="Lax",
            path="/",
        )
        return resp

    @app.get("/locale/<code>")
    def set_locale_redirect(code: str):
        """HTML form-friendly language switch — sets cookie and redirects back."""
        code = set_active_language(code)
        nxt = flask_request.args.get("next") or flask_request.referrer or "/"
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        resp = make_response(redirect(nxt))
        resp.set_cookie(
            LANG_COOKIE,
            code,
            max_age=60 * 60 * 24 * 365,
            samesite="Lax",
            path="/",
        )
        return resp
