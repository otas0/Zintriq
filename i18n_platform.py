"""Supported languages + runtime UI translation for MarketQR / Zintriq."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import g, has_app_context, has_request_context, request, session

_log = logging.getLogger("app.i18n")

# BCP 47 codes used for Builder *content* localization and marketing UI languages.
CONTENT_LOCALES: list[dict[str, str]] = [
    {"code": "en", "name": "English", "native": "English", "dir": "ltr"},
    {"code": "zh-Hans", "name": "Chinese (Simplified)", "native": "简体中文", "dir": "ltr"},
    {"code": "zh-Hant", "name": "Chinese (Traditional)", "native": "繁體中文", "dir": "ltr"},
    {"code": "ja", "name": "Japanese", "native": "日本語", "dir": "ltr"},
    {"code": "ko", "name": "Korean", "native": "한국어", "dir": "ltr"},
    {"code": "ms", "name": "Malay", "native": "Bahasa Melayu", "dir": "ltr"},
    {"code": "id", "name": "Indonesian", "native": "Bahasa Indonesia", "dir": "ltr"},
    {"code": "th", "name": "Thai", "native": "ไทย", "dir": "ltr"},
    {"code": "vi", "name": "Vietnamese", "native": "Tiếng Việt", "dir": "ltr"},
    {"code": "fil", "name": "Filipino", "native": "Filipino", "dir": "ltr"},
    {"code": "es", "name": "Spanish", "native": "Español", "dir": "ltr"},
    {"code": "pt-BR", "name": "Portuguese (Brazil)", "native": "Português (Brasil)", "dir": "ltr"},
    {"code": "pt", "name": "Portuguese", "native": "Português", "dir": "ltr"},
    {"code": "fr", "name": "French", "native": "Français", "dir": "ltr"},
    {"code": "de", "name": "German", "native": "Deutsch", "dir": "ltr"},
    {"code": "it", "name": "Italian", "native": "Italiano", "dir": "ltr"},
    {"code": "nl", "name": "Dutch", "native": "Nederlands", "dir": "ltr"},
    {"code": "sv", "name": "Swedish", "native": "Svenska", "dir": "ltr"},
    {"code": "da", "name": "Danish", "native": "Dansk", "dir": "ltr"},
    {"code": "fi", "name": "Finnish", "native": "Suomi", "dir": "ltr"},
    {"code": "no", "name": "Norwegian", "native": "Norsk", "dir": "ltr"},
    {"code": "pl", "name": "Polish", "native": "Polski", "dir": "ltr"},
    {"code": "cs", "name": "Czech", "native": "Čeština", "dir": "ltr"},
    {"code": "hu", "name": "Hungarian", "native": "Magyar", "dir": "ltr"},
    {"code": "ro", "name": "Romanian", "native": "Română", "dir": "ltr"},
    {"code": "el", "name": "Greek", "native": "Ελληνικά", "dir": "ltr"},
    {"code": "tr", "name": "Turkish", "native": "Türkçe", "dir": "ltr"},
    {"code": "ru", "name": "Russian", "native": "Русский", "dir": "ltr"},
    {"code": "uk", "name": "Ukrainian", "native": "Українська", "dir": "ltr"},
    {"code": "ar", "name": "Arabic", "native": "العربية", "dir": "rtl"},
    {"code": "he", "name": "Hebrew", "native": "עברית", "dir": "rtl"},
    {"code": "hi", "name": "Hindi", "native": "हिन्दी", "dir": "ltr"},
    {"code": "bn", "name": "Bengali", "native": "বাংলা", "dir": "ltr"},
    {"code": "ur", "name": "Urdu", "native": "اردو", "dir": "rtl"},
    {"code": "fa", "name": "Persian", "native": "فارسی", "dir": "rtl"},
    {"code": "ku", "name": "Kurdish", "native": "کوردی", "dir": "rtl"},
    {"code": "sw", "name": "Swahili", "native": "Kiswahili", "dir": "ltr"},
    {"code": "am", "name": "Amharic", "native": "አማርኛ", "dir": "ltr"},
    {"code": "af", "name": "Afrikaans", "native": "Afrikaans", "dir": "ltr"},
    {"code": "bg", "name": "Bulgarian", "native": "Български", "dir": "ltr"},
    {"code": "sk", "name": "Slovak", "native": "Slovenčina", "dir": "ltr"},
    {"code": "sl", "name": "Slovenian", "native": "Slovenščina", "dir": "ltr"},
    {"code": "lt", "name": "Lithuanian", "native": "Lietuvių", "dir": "ltr"},
    {"code": "lv", "name": "Latvian", "native": "Latviešu", "dir": "ltr"},
    {"code": "et", "name": "Estonian", "native": "Eesti", "dir": "ltr"},
    {"code": "sr", "name": "Serbian", "native": "Српски", "dir": "ltr"},
    {"code": "hr", "name": "Croatian", "native": "Hrvatski", "dir": "ltr"},
    {"code": "bs", "name": "Bosnian", "native": "Bosanski", "dir": "ltr"},
    {"code": "sq", "name": "Albanian", "native": "Shqip", "dir": "ltr"},
    {"code": "mk", "name": "Macedonian", "native": "Македонски", "dir": "ltr"},
    {"code": "is", "name": "Icelandic", "native": "Íslenska", "dir": "ltr"},
    {"code": "ca", "name": "Catalan", "native": "Català", "dir": "ltr"},
    {"code": "eu", "name": "Basque", "native": "Euskara", "dir": "ltr"},
    {"code": "ga", "name": "Irish", "native": "Gaeilge", "dir": "ltr"},
    {"code": "cy", "name": "Welsh", "native": "Cymraeg", "dir": "ltr"},
    {"code": "ka", "name": "Georgian", "native": "ქართული", "dir": "ltr"},
    {"code": "hy", "name": "Armenian", "native": "Հայերեն", "dir": "ltr"},
    {"code": "az", "name": "Azerbaijani", "native": "Azərbaycan", "dir": "ltr"},
    {"code": "kk", "name": "Kazakh", "native": "Қазақша", "dir": "ltr"},
    {"code": "km", "name": "Khmer", "native": "ខ្មែរ", "dir": "ltr"},
    {"code": "lo", "name": "Lao", "native": "ລາວ", "dir": "ltr"},
    {"code": "my", "name": "Burmese", "native": "မြန်မာ", "dir": "ltr"},
    {"code": "ne", "name": "Nepali", "native": "नेपाली", "dir": "ltr"},
    {"code": "si", "name": "Sinhala", "native": "සිංහල", "dir": "ltr"},
    {"code": "mn", "name": "Mongolian", "native": "Монгол", "dir": "ltr"},
    {"code": "so", "name": "Somali", "native": "Soomaali", "dir": "ltr"},
    {"code": "ha", "name": "Hausa", "native": "Hausa", "dir": "ltr"},
    {"code": "yo", "name": "Yoruba", "native": "Yorùbá", "dir": "ltr"},
    {"code": "zu", "name": "Zulu", "native": "isiZulu", "dir": "ltr"},
    {"code": "ta", "name": "Tamil", "native": "தமிழ்", "dir": "ltr"},
    {"code": "te", "name": "Telugu", "native": "తెలుగు", "dir": "ltr"},
    {"code": "be", "name": "Belarusian", "native": "Беларуская", "dir": "ltr"},
    {"code": "mt", "name": "Maltese", "native": "Malti", "dir": "ltr"},
    {"code": "jv", "name": "Javanese", "native": "Basa Jawa", "dir": "ltr"},
    {"code": "ps", "name": "Pashto", "native": "پښتو", "dir": "rtl"},
    {"code": "dv", "name": "Divehi", "native": "ދިވެހި", "dir": "rtl"},
    {"code": "fo", "name": "Faroese", "native": "Føroyskt", "dir": "ltr"},
    {"code": "kl", "name": "Greenlandic", "native": "Kalaallisut", "dir": "ltr"},
    {"code": "ky", "name": "Kyrgyz", "native": "Кыргызча", "dir": "ltr"},
    {"code": "tg", "name": "Tajik", "native": "Тоҷикӣ", "dir": "ltr"},
    {"code": "tk", "name": "Turkmen", "native": "Türkmençe", "dir": "ltr"},
    {"code": "uz", "name": "Uzbek", "native": "Oʻzbekcha", "dir": "ltr"},
    {"code": "ti", "name": "Tigrinya", "native": "ትግርኛ", "dir": "ltr"},
    {"code": "mg", "name": "Malagasy", "native": "Malagasy", "dir": "ltr"},
    {"code": "mi", "name": "Māori", "native": "Te Reo Māori", "dir": "ltr"},
    {"code": "lb", "name": "Luxembourgish", "native": "Lëtzebuergesch", "dir": "ltr"},
    {"code": "rm", "name": "Romansh", "native": "Rumantsch", "dir": "ltr"},
    {"code": "bo", "name": "Tibetan", "native": "བོད་སྐད་", "dir": "ltr"},
    {"code": "ii", "name": "Sichuan Yi", "native": "ꆈꌠ꒿ Nuosu", "dir": "ltr"},
    {"code": "ain", "name": "Ainu", "native": "アイヌ・イタㇰ", "dir": "ltr"},
    {"code": "yoi", "name": "Yonaguni", "native": "与那国物言", "dir": "ltr"},
    {"code": "rys", "name": "Yaeyama", "native": "八重山物言", "dir": "ltr"},
    {"code": "twm", "name": "Monpa (Tawang)", "native": "Monpa", "dir": "ltr"},
    {"code": "nuf", "name": "Nusu", "native": "Nusu", "dir": "ltr"},
    {"code": "jiu", "name": "Jino", "native": "基诺语", "dir": "ltr"},
    {"code": "duu", "name": "Dulong", "native": "独龙语", "dir": "ltr"},
    {"code": "evn", "name": "Evenki", "native": "Эвэды̄ турэ̄н", "dir": "ltr"},
    {"code": "gld", "name": "Nanai", "native": "нанай хэсэни", "dir": "ltr"},
    {"code": "bdk", "name": "Budukh", "native": "Будад мез", "dir": "ltr"},
    {"code": "kjj", "name": "Khinalug", "native": "каьтш мицӀ", "dir": "ltr"},
    {"code": "aem", "name": "Arem", "native": "Arem", "dir": "ltr"},
    {"code": "kum", "name": "Kumzari", "native": "کومزاری", "dir": "rtl"},
    {"code": "ntz", "name": "Natanzi", "native": "نطنزی", "dir": "rtl"},
    {"code": "grk", "name": "Griko", "native": "Γκρίκο", "dir": "ltr"},
    {"code": "lld", "name": "Ladin", "native": "Ladin", "dir": "ltr"},
    {"code": "oc", "name": "Occitan", "native": "Occitan", "dir": "ltr"},
    {"code": "ruo", "name": "Istro-Romanian", "native": "vlåșește", "dir": "ltr"},
    {"code": "se", "name": "Northern Sámi", "native": "Davvisámegiella", "dir": "ltr"},
    {"code": "br", "name": "Breton", "native": "Brezhoneg", "dir": "ltr"},
    {"code": "sbf", "name": "Shabo", "native": "Shabo", "dir": "ltr"},
    {"code": "ahg", "name": "Qimant", "native": "Qimant", "dir": "ltr"},
    {"code": "xuu", "name": "Khwe", "native": "Khwe", "dir": "ltr"},
    {"code": "abo", "name": "Abon", "native": "Abõ", "dir": "ltr"},
    {"code": "aja", "name": "Aja", "native": "Aja", "dir": "ltr"},
    {"code": "nv", "name": "Navajo", "native": "Diné bizaad", "dir": "ltr"},
    {"code": "cr", "name": "Cree", "native": "Nēhiyawēwin", "dir": "ltr"},
    {"code": "oj", "name": "Ojibwe", "native": "Anishinaabemowin", "dir": "ltr"},
    {"code": "kic", "name": "Kickapoo", "native": "Kikapú", "dir": "ltr"},
    {"code": "nah", "name": "Nahuatl", "native": "Nāhuatl", "dir": "ltr"},
    {"code": "yua", "name": "Yucatec Maya", "native": "Màaya t'àan", "dir": "ltr"},
    {"code": "quc", "name": "K'iche'", "native": "K'iche'", "dir": "ltr"},
    {"code": "zap", "name": "Zapotec", "native": "Diidxazá", "dir": "ltr"},
    {"code": "mix", "name": "Mixtec", "native": "Tu'un savi", "dir": "ltr"},
    {"code": "qu", "name": "Quechua", "native": "Runa Simi", "dir": "ltr"},
    {"code": "gn", "name": "Guarani", "native": "Avañe'ẽ", "dir": "ltr"},
    {"code": "ay", "name": "Aymara", "native": "Aymar aru", "dir": "ltr"},
    {"code": "enq", "name": "Enga", "native": "Enga", "dir": "ltr"},
    {"code": "hui", "name": "Huli", "native": "Huli", "dir": "ltr"},
    {"code": "pjt", "name": "Pitjantjatjara", "native": "Pitjantjatjara", "dir": "ltr"},
    {"code": "wbp", "name": "Warlpiri", "native": "Warlpiri", "dir": "ltr"},
    {"code": "rap", "name": "Rapa Nui", "native": "Vananga Rapa Nui", "dir": "ltr"},
    {"code": "haw", "name": "Hawaiian", "native": "ʻŌlelo Hawaiʻi", "dir": "ltr"},
]

# Back-compat alias — prefer CONTENT_LOCALES or language_options() for UI.
SUPPORTED_LANGUAGES = CONTENT_LOCALES

# Public language menu: complete product UI (English + Chinese). Other catalogs
# stay on /locale/<code> and the translate page.
PRODUCT_UI_LANGUAGES = ("en", "zh-Hans", "zh-Hant")

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
    "pt-br": "pt-BR",
    "pt-pt": "pt",
    "nb": "no",
    "nn": "no",
    "tl": "fil",
    "iw": "he",
    "hi-in": "hi",
    "bn-bd": "bn",
    "bn-in": "bn",
    "ur-pk": "ur",
    "ur-in": "ur",
    "fa-ir": "fa",
    "fa-af": "fa",
    "ku-iq": "ku",
    "ckb": "ku",
    "sw-ke": "sw",
    "sw-tz": "sw",
    "am-et": "am",
    "af-za": "af",
    "bg-bg": "bg",
    "sk-sk": "sk",
    "sl-si": "sl",
    "lt-lt": "lt",
    "lv-lv": "lv",
    "et-ee": "et",
    "sr-rs": "sr",
    "sr-latn": "sr",
    "sr-cyrl": "sr",
    "hr-hr": "hr",
    "bs-ba": "bs",
    "sq-al": "sq",
    "mk-mk": "mk",
    "is-is": "is",
    "ca-es": "ca",
    "eu-es": "eu",
    "ga-ie": "ga",
    "cy-gb": "cy",
    "ka-ge": "ka",
    "hy-am": "hy",
    "az-az": "az",
    "kk-kz": "kk",
    "km-kh": "km",
    "lo-la": "lo",
    "my-mm": "my",
    "ne-np": "ne",
    "si-lk": "si",
    "mn-mn": "mn",
    "so-so": "so",
    "ha-ng": "ha",
    "yo-ng": "yo",
    "zu-za": "zu",
    "ta-in": "ta",
    "ta-lk": "ta",
    "te-in": "te",
    "be-by": "be",
    "mt-mt": "mt",
    "jv-id": "jv",
    "ps-af": "ps",
    "dv-mv": "dv",
    "fo-fo": "fo",
    "kl-gl": "kl",
    "ky-kg": "ky",
    "tg-tj": "tg",
    "tk-tm": "tk",
    "uz-uz": "uz",
    "ti-er": "ti",
    "mg-mg": "mg",
    "mi-nz": "mi",
    "lb-lu": "lb",
    "rm-ch": "rm",
    "bo-cn": "bo",
    "bo-in": "bo",
    "bo-bt": "bo",
    "ii-cn": "ii",
    "se-no": "se",
    "se-se": "se",
    "se-fi": "se",
    "sme": "se",
    "br-fr": "br",
    "bre": "br",
    "nv-us": "nv",
    "qu-pe": "qu",
    "qu-bo": "qu",
    "qu-ec": "qu",
    "gn-py": "gn",
    "ay-bo": "ay",
    "ay-pe": "ay",
    "haw-us": "haw",
    "nah-mx": "nah",
    "nhe": "nah",
    "yua-mx": "yua",
    "quc-gt": "quc",
    "lld-it": "lld",
    "oc-fr": "oc",
    "oc-it": "oc",
}


def supported_language_codes() -> set[str]:
    return {item["code"] for item in CONTENT_LOCALES}


def shipped_ui_language_codes() -> set[str]:
    """Codes with a locale JSON catalog on disk (product chrome UI)."""
    if not _LOCALES_DIR.is_dir():
        return {DEFAULT_LANGUAGE}
    codes = {
        path.stem
        for path in _LOCALES_DIR.glob("*.json")
        if path.is_file() and path.stem in supported_language_codes()
    }
    return codes or {DEFAULT_LANGUAGE}


def language_meta(code: str) -> dict[str, str]:
    code = normalize_language(code)
    for item in CONTENT_LOCALES:
        if item["code"] == code:
            return dict(item)
    return dict(CONTENT_LOCALES[0])


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
    """Picker entries for the public language menu (English and Chinese)."""
    wanted = set(PRODUCT_UI_LANGUAGES)
    return [dict(item) for item in CONTENT_LOCALES if item["code"] in wanted]


def content_locale_options() -> list[dict[str, str]]:
    """Builder content-translation locales (may lack UI catalogs)."""
    return [dict(item) for item in CONTENT_LOCALES]


@lru_cache(maxsize=256)
def _load_locale_mtime(code: str, mtime: int) -> dict[str, str]:
    """Load one locale catalog. Missing files return {} so translate() falls back per-key to en."""
    path = _LOCALES_DIR / f"{code}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _log.debug("locale_file_load_failed", extra={"op": "_load_locale"})
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _load_locale(code: str) -> dict[str, str]:
    code = normalize_language(code)
    path = _LOCALES_DIR / f"{code}.json"
    try:
        mtime = int(path.stat().st_mtime) if path.is_file() else 0
    except OSError:
        mtime = 0
    return _load_locale_mtime(code, mtime)


def clear_locale_cache() -> None:
    _load_locale_mtime.cache_clear()
    _core_coverage.cache_clear()


def _fallback_chain(code: str) -> list[str]:
    from site_config import DEFAULT_LOCALE_FALLBACK, LOCALE_FALLBACKS

    chain = [code]
    for item in LOCALE_FALLBACKS.get(code, DEFAULT_LOCALE_FALLBACK):
        if item not in chain:
            chain.append(item)
    if DEFAULT_LANGUAGE not in chain:
        chain.append(DEFAULT_LANGUAGE)
    return chain


def _lookup(key: str, code: str) -> tuple[str | None, str | None]:
    for lang in _fallback_chain(code):
        text = _load_locale(lang).get(key)
        if text is not None:
            return text, lang
    return None, None


def plural_category(lang: str, count: Any) -> str:
    """CLDR plural category for keys that interpolate {n}. Missing Babel yields 'other'."""
    try:
        number = int(count)
    except (TypeError, ValueError):
        try:
            number = float(count)
        except (TypeError, ValueError):
            return "other"
    try:
        from babel import Locale

        return Locale.parse(str(lang).replace("-", "_")).plural_form(number)
    except Exception:
        _log.debug("plural_category_failed", exc_info=True, extra={"op": "plural_category"})
        return "one" if number == 1 else "other"


def _note_fallback(requested: str, found: str | None) -> None:
    if not found or found == requested or not has_request_context():
        return
    g.i18n_partial = True
    g.i18n_fallback_lang = found


_LEGAL_DOC_PREFIXES = (
    "legal.privacy.",
    "legal.terms.",
    "legal.cookies.",
    "legal.imprint.",
)


def _legal_source_lang(code: str, key: str) -> str:
    """Legal documents: English and Simplified Chinese only. Community locales do not override."""
    if key not in {"legal.lang_notice", "legal.draft_notice"} and not key.startswith(_LEGAL_DOC_PREFIXES):
        return code
    if code == "zh-Hans" or code.lower().startswith("zh"):
        return "zh-Hans"
    return "en"


def translate(key: str, lang: str | None = None, **vars: Any) -> str:
    """Translate a message key. Missing keys walk LOCALE_FALLBACKS, then English."""
    code = normalize_language(lang or get_active_language())
    code = _legal_source_lang(code, key)
    text = None
    found = None
    if "n" in vars:
        text, found = _lookup(f"{key}.{plural_category(code, vars['n'])}", code)
    if text is None:
        text, found = _lookup(key, code)
    _note_fallback(code, found)
    if text is None:
        text = key
    if vars:
        try:
            text = text.format(**{k: vars[k] for k in vars})
        except (KeyError, ValueError):
            _log.debug("translate_format_failed", exc_info=True, extra={"op": "translate"})
            pass
    return text


@lru_cache(maxsize=256)
def _core_coverage(code: str) -> float:
    from site_config import CORE_MESSAGE_KEYS

    if not CORE_MESSAGE_KEYS:
        return 1.0
    catalog = _load_locale(code)
    hit = sum(1 for key in CORE_MESSAGE_KEYS if catalog.get(key))
    return hit / len(CORE_MESSAGE_KEYS)


def core_coverage(code: str) -> float:
    return _core_coverage(normalize_language(code))


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


def _language_return_path(raw: str | None) -> str:
    """Stay on the current page after a language change; drop hl so the cookie wins."""
    value = str(raw or "").strip()
    if "://" in value:
        try:
            split = urlsplit(value)
            value = urlunsplit(("", "", split.path or "/", split.params, split.query, ""))
        except ValueError:
            value = "/"
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    parts = urlsplit(value)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "hl"]
    path = parts.path or "/"
    encoded = urlencode(query)
    return f"{path}?{encoded}" if encoded else path


def resolve_request_language() -> str:
    """Priority: explicit session → cookie → browser Accept-Language → en.

    Any CONTENT_LOCALES code is accepted so market regions (e.g. /et → am) keep
    their language even before a full catalog ships; missing keys fall back to en.
    The language picker still lists shipped catalogs via language_options().
    """
    allowed = supported_language_codes()

    def _accept(code: str) -> str:
        code = normalize_language(code)
        return code if code in allowed else DEFAULT_LANGUAGE

    hl = request.args.get("hl")
    if hl:
        return _accept(hl)

    raw = session.get(LANG_SESSION_KEY)
    if raw:
        return _accept(raw)
    cookie = request.cookies.get(LANG_COOKIE)
    if cookie:
        return _accept(cookie)

    for item, _quality in request.accept_languages:
        key = str(item or "").strip().replace("_", "-")
        if not key:
            continue
        lower = key.lower()
        for code in allowed:
            if code.lower() == lower:
                return code
        mapped = _ALIASES.get(lower)
        if mapped and mapped in allowed:
            return mapped
        primary = lower.split("-", 1)[0]
        if primary == "zh":
            if "tw" in lower or "hk" in lower or "hant" in lower:
                return "zh-Hant" if "zh-Hant" in allowed else DEFAULT_LANGUAGE
            return "zh-Hans" if "zh-Hans" in allowed else DEFAULT_LANGUAGE
        for code in allowed:
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
        catalog = _load_locale(lang)
        en_catalog = _load_locale(DEFAULT_LANGUAGE)
        # Client toast/alert bag: English msgids (flash/JS), not dotted product keys
        dotted = re.compile(r"^[a-z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_.]+)+$")
        js_messages = {}
        for key, en_text in en_catalog.items():
            if dotted.match(str(key)):
                continue
            js_messages[str(key)] = catalog.get(key) or en_text

        def _(key: str, **vars: Any) -> str:
            return translate(key, lang, **vars)

        from site_config import CORE_MESSAGE_KEYS

        for core_key in CORE_MESSAGE_KEYS:
            translate(core_key, lang)

        fallback_code = getattr(g, "i18n_fallback_lang", None) or DEFAULT_LANGUAGE
        fallback_meta = language_meta(fallback_code)
        return {
            "_": _,
            "t": _,
            "ui_lang": lang,
            "ui_lang_dir": meta.get("dir", "ltr"),
            "ui_languages": language_options(),
            "content_locales": content_locale_options(),
            "html_lang": lang,
            "ui_js_messages": js_messages,
            "i18n_partial": bool(getattr(g, "i18n_partial", False)),
            "i18n_fallback_name": fallback_meta.get("native") or fallback_meta.get("name") or fallback_code,
            "i18n_active_name": meta.get("native") or meta.get("name") or lang,
        }

    @app.get("/api/languages")
    def api_languages():
        return jsonify({
            "languages": language_options(),
            "content_locales": content_locale_options(),
            "default": DEFAULT_LANGUAGE,
            "active": get_active_language(),
            "note": "languages = shipped product UI catalogs; content_locales = Builder field translation targets",
        })

    @app.post("/api/locale")
    def api_set_locale():
        data = flask_request.get_json(silent=True) or {}
        requested = normalize_language(
            data.get("language") or flask_request.form.get("language")
        )
        code = requested if requested in supported_language_codes() else DEFAULT_LANGUAGE
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
        requested = normalize_language(code)
        code = set_active_language(
            requested if requested in supported_language_codes() else DEFAULT_LANGUAGE
        )
        nxt = _language_return_path(
            flask_request.args.get("next") or flask_request.referrer or flask_request.path
        )
        resp = make_response(redirect(nxt))
        resp.set_cookie(
            LANG_COOKIE,
            code,
            max_age=60 * 60 * 24 * 365,
            samesite="Lax",
            path="/",
        )
        return resp