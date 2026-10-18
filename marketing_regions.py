"""Marketing region slugs, detection, and localized routing (/jp, /de, …)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable
from urllib.parse import unquote

from flask import Flask, abort, current_app, g, has_app_context, redirect, render_template, request, session, url_for

from marketing_markets_data import GROUP_LABELS, GROUP_ORDER, MARKET_ROWS

_log = logging.getLogger("app.marketing_regions")

MARKET_COOKIE = "mq_market"
MARKET_CHOICE_COOKIE = "mq_market_chosen"
REGION_HINT_DISMISS_COOKIE = "mq_region_hint_dismiss"

# Cache key for "look up the caller's public egress IP" (localhost / private clients).
_EGRESS_GEO_KEY = "__egress__"

# Slugs must not collide with top-level app routes.
RESERVED_ROOT_SEGMENTS = frozenset(
    {
        "app",
        "api",
        "login",
        "register",
        "logout",
        "manage",
        "store",
        "place",
        "build",
        "activate",
        "contact",
        "templates",
        "pricing",
        "download",
        "primitives",
        "blog",
        "docs",
        "plugins",
        "about",
        "extend",
        "security",
        "connections",
        "customers",
        "changelog",
        "compositions",
        "how-it-works",
        "compare",
        "choose-region",
        "locale",
        "legal",
        "static",
        "health",
        "healthz",
        "readyz",
        "my-stores",
        "create",
        "checkin",
        "magic-link",
        "forgot-password",
        "reset-password",
        "account",
        "home",
        "favicon.ico",
        "robots.txt",
        "community",
        "studio",
        "product",
        "hardware",
        "translate",
        "maintenance",
        "billing",
        "checkout",
        "webhooks",
    }
)


@dataclass(frozen=True)
class Market:
    slug: str
    language: str
    name: str
    native: str
    countries: frozenset[str]
    group: str

    @property
    def region_name(self) -> str:
        native = (self.native or "").strip()
        if native.endswith("）") and "（" in native:
            inner = native[native.rfind("（") + 1 : -1].strip()
            if inner:
                return inner
        return native or self.name


MARKETS: tuple[Market, ...] = tuple(
    Market(slug, lang, name, native, countries, group)
    for slug, lang, name, native, countries, group in MARKET_ROWS
)

MARKET_BY_SLUG = {m.slug: m for m in MARKETS}
MARKET_SLUGS = frozenset(MARKET_BY_SLUG.keys())

# ISO country → candidate market slugs (multi-lang countries have several).
_COUNTRY_TO_SLUGS: dict[str, list[str]] = {}
for _m in MARKETS:
    for _c in _m.countries:
        _COUNTRY_TO_SLUGS.setdefault(_c, []).append(_m.slug)

INTL_SLUG = "intl"

# Old single-slug bookmarks → multi-language primary slug.
LEGACY_SLUG_REDIRECTS = {
    "bo": "bo-es",
    "py": "py-es",
    "in": "in-en",
    "ie": "ie-en",
    "za": "za-en",
    "ng": "ng-en",
    "af": "af-fa",
    "er": "er-en",
    "mg": "mg-fr",
    "mv": "mv-en",
    "nz": "nz-en",
    "fo": "fo-fo",
    "gl": "gl-kl",
    "kg": "kg-ky",
    "tj": "tj-tg",
    "tm": "tm-tk",
    "uz": "uz-uz",
}


def market_from_path(path: str) -> str | None:
    seg = (path or "/").strip("/").split("/", 1)[0].lower()
    if not seg or seg in RESERVED_ROOT_SEGMENTS:
        return None
    if seg in MARKET_SLUGS:
        return seg
    return None


def region_display_name(market: Market | None) -> str:
    """Country/region label without a language prefix (语言在语言选择器里另选)."""
    if market is None:
        return ""
    return market.region_name


def _primary_markets() -> list[Market]:
    """One market per country; first catalog row is the default language for that region."""
    seen: set[frozenset[str]] = set()
    out: list[Market] = []
    for market in MARKETS:
        key = market.countries or frozenset({market.slug})
        if key in seen:
            continue
        seen.add(key)
        out.append(market)
    return out


def market_groups_for_picker() -> list[dict]:
    primaries = _primary_markets()
    out: list[dict] = []
    for gid in GROUP_ORDER:
        items = [m for m in primaries if m.group == gid]
        if not items:
            continue
        out.append(
            {
                "id": gid,
                "label_key": f"group.{gid}",
                "label": GROUP_LABELS[gid],
                "markets": items,
            }
        )
    return out


def _client_ip() -> str | None:
    for header in ("CF-Connecting-IP", "True-Client-IP", "X-Real-IP"):
        raw = (request.headers.get(header) or "").strip()
        if raw:
            return raw.split(",")[0].strip()
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return (request.remote_addr or "").strip() or None


def _is_private_ip(ip: str) -> bool:
    if not ip:
        return True
    if ip in ("::1", "0.0.0.0"):
        return True
    if ip.startswith("127.") or ip.startswith("10.") or ip.startswith("192.168."):
        return True
    if ip.startswith("172."):
        try:
            second = int(ip.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (IndexError, ValueError):
            pass
    if ip.startswith("fc") or ip.startswith("fd") or ip.startswith("fe80:"):
        return True
    return False


def _normalize_country_code(raw: str | None) -> str | None:
    cc = str(raw or "").strip().upper()
    if len(cc) == 2 and cc.isalpha() and cc not in ("XX", "T1", "ZZ"):
        return cc
    return None


def _lookup_country_ip_api(ip: str | None) -> str | None:
    """ip-api.com — omit IP to resolve the requestor's public egress address."""
    import json
    import urllib.request

    path = f"/{ip}" if ip else ""
    url = f"http://ip-api.com/json{path}?fields=status,countryCode,message"
    req = urllib.request.Request(url, headers={"User-Agent": "ZintriqMarketGeo/1.0"})
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if data.get("status") == "success":
        return _normalize_country_code(data.get("countryCode"))
    return None


def _lookup_country_country_is(ip: str | None) -> str | None:
    """api.country.is fallback (HTTPS; omit IP for egress)."""
    import json
    import urllib.request

    path = f"/{ip}" if ip else ""
    url = f"https://api.country.is{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "ZintriqMarketGeo/1.0"})
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return _normalize_country_code(data.get("country"))


@lru_cache(maxsize=512)
def _country_from_ip_cached(ip: str) -> str:
    """Best-effort country for an IP (or egress when ip == _EGRESS_GEO_KEY).

    Returns ISO code or "" on miss (empty string so lru_cache stays hashable/truthy-safe).
    """
    query_ip: str | None
    if ip == _EGRESS_GEO_KEY:
        query_ip = None
    else:
        query_ip = ip
    for lookup in (_lookup_country_ip_api, _lookup_country_country_is):
        try:
            cc = lookup(query_ip)
            if cc:
                return cc
        except Exception:
            _log.debug(
                "ip_geo_lookup_failed",
                exc_info=True,
                extra={"op": "_country_from_ip_cached", "provider": lookup.__name__},
            )
    return ""


def _env_geo_country() -> str | None:
    for key in ("MQ_GEO_COUNTRY", "GEO_COUNTRY_OVERRIDE"):
        cc = _normalize_country_code(os.environ.get(key))
        if cc:
            return cc
    return None


def _allow_egress_geo_fallback(client_ip: str | None) -> bool:
    """Use server egress IP geo only when the browser IP is unusable (localhost/LAN).

    Never use egress for a missing/public client IP in production — that would
    pin every visitor to the datacenter country.
    """
    flag = (os.environ.get("MQ_GEO_EGRESS_FALLBACK") or "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    if flag in ("1", "true", "yes", "on"):
        return True
    if has_app_context():
        try:
            if current_app.debug:
                return True
        except Exception:
            pass
    if not client_ip:
        return False
    # Loopback always — local `python app.py` + browser on 127.0.0.1.
    if client_ip in ("::1",) or client_ip.startswith("127."):
        return True
    # Private LAN only when explicitly developing (DEBUG already covered above).
    return False


def _geo_country_code() -> str | None:
    # Explicit debug / QA override (?cc=CN) — wins when present so local testing works.
    debug = _normalize_country_code(request.args.get("cc"))
    if debug:
        return debug
    env_cc = _env_geo_country()
    if env_cc:
        return env_cc
    for header in (
        "CF-IPCountry",
        "X-Vercel-IP-Country",
        "CloudFront-Viewer-Country",
        "X-AppEngine-Country",
        "X-Country-Code",
        "X-Geo-Country",
        "Fastly-Client-Country",
    ):
        raw = _normalize_country_code(request.headers.get(header))
        if raw:
            return raw
    # Public client IP (CDN-forwarded or direct).
    ip = _client_ip()
    if ip and not _is_private_ip(ip):
        cc = _country_from_ip_cached(ip)
        if cc:
            return cc
    # Localhost / debug: resolve the machine's public egress IP (ip-api with no query).
    if _allow_egress_geo_fallback(ip):
        cc = _country_from_ip_cached(_EGRESS_GEO_KEY)
        if cc:
            return cc
    return None


def _normalize_market_slug(slug: str | None) -> str | None:
    if not slug:
        return None
    slug = slug.lower().strip()
    slug = LEGACY_SLUG_REDIRECTS.get(slug, slug)
    return slug if slug in MARKET_SLUGS else None


def _pick_slug_for_country(cc: str) -> str | None:
    candidates = _COUNTRY_TO_SLUGS.get(cc) or []
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Multi-language country: prefer Accept-Language match.
    for item, _q in request.accept_languages:
        key = str(item or "").strip().replace("_", "-").lower()
        if not key:
            continue
        primary = key.split("-", 1)[0]
        for slug in candidates:
            lang = MARKET_BY_SLUG[slug].language.lower()
            lang_primary = lang.split("-", 1)[0]
            if key == lang or key.startswith(lang_primary) or lang_primary == primary:
                return slug
    return candidates[0]


def _market_from_accept_language() -> str | None:
    """Map Accept-Language to a market slug.

    Prefer BCP-47 region tags (e.g. en-MY → Malaysia) over bare language matches
    so ms-MY does not land on the first Malay market (Brunei).
    """
    for item, _q in request.accept_languages:
        key = str(item or "").strip().replace("_", "-")
        if not key:
            continue
        lower = key.lower()
        parts = lower.split("-")
        primary = parts[0]
        region = ""
        for part in parts[1:]:
            if len(part) == 2 and part.isalpha():
                region = part.upper()
                break

        # Region tag → country market (highest signal after CDN geo).
        if region:
            picked = _pick_slug_for_country(region)
            if picked:
                return picked

        if primary == "zh":
            if any(x in lower for x in ("tw", "hant")):
                return "tw"
            if any(x in lower for x in ("hk", "mo")):
                return "hk"
            return "cn"
        if primary == "pt":
            return "br" if "br" in lower else "pt"
        if primary == "en":
            # Bare English with no region → do not guess a country (avoid pinning CN users to /us).
            continue
        if primary == "fr" and region == "CA":
            return "ca-fr"
        if primary == "nl" and region == "BE":
            return "be-nl"
        if primary == "fr" and region == "BE":
            return "be-fr"
        if primary == "de" and region == "CH":
            return "ch-de"
        if primary == "fr" and region == "CH":
            return "ch-fr"
        if primary == "it" and region == "CH":
            return "ch-it"

        # Exact language code match (zh-Hans, pt-BR, …).
        for m in MARKETS:
            if m.language.lower() == lower:
                return m.slug

        # Curated primary market per language (avoid first-hit Brunei for ms, etc.).
        lang_home = {
            "ar": "sa",
            "he": "il",
            "fa": "ir",
            "hi": "in-hi",
            "bn": "bd",
            "ur": "pk",
            "ja": "jp",
            "ko": "kr",
            "th": "th",
            "vi": "vn",
            "id": "id",
            "ms": "my",
            "fil": "ph",
            "tr": "tr",
            "ru": "ru",
            "uk": "ua",
            "de": "de",
            "fr": "fr",
            "es": "es-es",
            "it": "it",
            "nl": "nl",
            "pl": "pl",
            "sv": "se",
            "da": "dk",
            "fi": "fi",
            "no": "no",
            "cs": "cz",
            "hu": "hu",
            "ro": "ro",
            "el": "gr",
            "bg": "bg",
            "sk": "sk",
            "sl": "si",
            "hr": "hr",
            "sr": "rs",
            "bs": "ba",
            "sq": "al",
            "mk": "mk",
            "am": "et",
            "sw": "ke",
            "ha": "ng-ha",
            "yo": "ng-yo",
            "zu": "za-zu",
            "af": "za-af",
            "ta": "in-ta",
            "te": "in-te",
            "si": "lk",
            "ne": "np",
            "my": "mm",
            "km": "kh",
            "lo": "la",
            "mn": "mn",
            "ka": "ge",
            "hy": "am",
            "az": "az",
            "kk": "kz",
            "be": "by",
            "ga": "ie-ga",
            "cy": "gb-cy",
            "mt": "mt",
            "is": "is",
            "ca": "es-ca",
            "eu": "es-eu",
            "jv": "id-jv",
            "ps": "af-ps",
            "dv": "mv-dv",
            "ky": "kg-ky",
            "tg": "tj-tg",
            "tk": "tm-tk",
            "uz": "uz-uz",
            "ti": "er-ti",
            "mg": "mg-mg",
            "mi": "nz-mi",
            "lb": "lu-lb",
            "rm": "ch-rm",
            "fo": "fo-fo",
            "kl": "gl-kl",
            "so": "so",
            "ku": "iq",
            "bo": "cn-bo",
            "ii": "cn-ii",
            "ain": "jp-ain",
            "yoi": "jp-yoi",
            "rys": "jp-rys",
            "twm": "cn-twm",
            "nuf": "cn-nuf",
            "jiu": "cn-jiu",
            "duu": "cn-duu",
            "evn": "cn-evn",
            "gld": "cn-gld",
            "bdk": "az-bdk",
            "kjj": "az-kjj",
            "aem": "la-aem",
            "kum": "om-kum",
            "ntz": "ir-ntz",
            "grk": "it-grk",
            "lld": "it-lld",
            "oc": "fr-oc",
            "ruo": "hr-ruo",
            "se": "no-smi",
            "br": "fr-br",
            "sbf": "et-sbf",
            "ahg": "et-ahg",
            "xuu": "na-xuu",
            "abo": "cm-abo",
            "aja": "ss-aja",
            "nv": "us-nv",
            "cr": "ca-cr",
            "oj": "ca-oj",
            "kic": "us-kic",
            "nah": "mx-nah",
            "yua": "mx-yua",
            "quc": "gt-quc",
            "zap": "mx-zap",
            "mix": "mx-mix",
            "qu": "pe-qu",
            "gn": "py-gn",
            "ay": "bo-ay",
            "enq": "pg-enq",
            "hui": "pg-hui",
            "pjt": "au-pjt",
            "wbp": "au-wbp",
            "rap": "cl-rap",
            "haw": "us-haw",
        }
        home = lang_home.get(primary)
        if home:
            return home
    return None


def detect_market_slug() -> str | None:
    """Best-effort market slug from CDN/IP geo, then Accept-Language."""
    cc = _geo_country_code()
    if cc:
        picked = _normalize_market_slug(_pick_slug_for_country(cc))
        if picked:
            return picked
    return _normalize_market_slug(_market_from_accept_language())


def markets_for_detected_country() -> list[Market]:
    """Primary region for the detected country (language is chosen separately)."""
    cc = _geo_country_code()
    slugs: list[str] = []
    if cc and _COUNTRY_TO_SLUGS.get(cc):
        slugs = [_COUNTRY_TO_SLUGS[cc][0]]
    if not slugs:
        picked = detect_market_slug()
        market = MARKET_BY_SLUG.get(picked or "")
        if market and market.countries:
            country = sorted(market.countries)[0]
            country_slugs = _COUNTRY_TO_SLUGS.get(country) or [market.slug]
            slugs = [country_slugs[0]]
        elif market:
            slugs = [market.slug]
    out: list[Market] = []
    seen: set[str] = set()
    for slug in slugs:
        market = MARKET_BY_SLUG.get(slug)
        if market and slug not in seen:
            seen.add(slug)
            out.append(market)
    return out


def current_browsing_market_slug() -> str | None:
    """Market the user is currently viewing (path prefix, else remembered choice)."""
    slug = getattr(g, "market_slug", None)
    if slug and slug in MARKET_SLUGS:
        return slug
    chosen = request.cookies.get(MARKET_CHOICE_COOKIE) or session.get("market_chosen")
    if chosen == INTL_SLUG:
        return INTL_SLUG
    return _normalize_market_slug(str(chosen or ""))


def region_mismatch_hint() -> dict | None:
    """Popup payload when geo-detected region differs from the site being viewed.

    Uses CDN/IP country only (not Accept-Language) so browser language prefs
    do not nag users who intentionally picked another regional site.
    Returns None when aligned, unknown, on the picker, or user dismissed this pair.
    """
    path = request.path or "/"
    if path == "/choose-region" or path.startswith("/choose-region/"):
        return None
    if path.startswith("/static/") or path.startswith("/api/"):
        return None
    # Auth / app shells: keep the hint on public marketing surfaces only.
    if path.startswith(
        (
            "/app/",
            "/bos/",
            "/owner/",
            "/api/",
            "/login",
            "/register",
            "/logout",
            "/forgot-password",
            "/reset-password",
            "/magic-link",
            "/two-factor",
        )
    ):
        return None

    cc = _geo_country_code()
    if not cc:
        return None
    detected = _normalize_market_slug(_pick_slug_for_country(cc))
    if not detected:
        return None
    detected_m = MARKET_BY_SLUG.get(detected)
    if not detected_m:
        return None

    current = current_browsing_market_slug()
    if not current:
        return None
    if current == detected:
        return None

    # Same country, different language variant (e.g. ca-en vs ca-fr) — no nag.
    if current != INTL_SLUG:
        current_m = MARKET_BY_SLUG.get(current)
        if current_m and current_m.countries and detected_m.countries:
            if current_m.countries & detected_m.countries:
                return None

    dismiss_key = f"{current}|{detected}"
    raw_dismiss = unquote(request.cookies.get(REGION_HINT_DISMISS_COOKIE) or "")
    if raw_dismiss == dismiss_key:
        return None

    display_name = region_display_name(detected_m) or detected_m.name
    return {
        "current_slug": current,
        "detected_slug": detected,
        "detected_name": detected_m.name,
        "detected_native": detected_m.native,
        "detected_display": display_name,
        "dismiss_key": dismiss_key,
        "go_url": url_for("marketing_choose_region_go", slug=detected),
    }


def apply_market_language(slug: str) -> None:
    """Bind the market to this request. UI language is chosen separately."""
    market = MARKET_BY_SLUG.get(slug)
    if not market:
        return
    g.market_slug = slug
    g.market = market


def market_prefix(slug: str | None = None) -> str:
    s = slug or getattr(g, "market_slug", None)
    if not s or s == INTL_SLUG:
        return ""
    return f"/{s}"


def url_for_marketing_path(path: str = "") -> str:
    prefix = market_prefix()
    p = path if path.startswith("/") or not path else f"/{path}"
    if not p or p == "/":
        return prefix or "/"
    return f"{prefix}{p}" if prefix else p


def _persist_market_choice(slug: str, response):
    """Remember the country/region. Language stays on the language cookie."""
    session["market_chosen"] = slug
    session.modified = True
    response.set_cookie(
        MARKET_CHOICE_COOKIE,
        slug,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        path="/",
    )
    response.set_cookie(
        MARKET_COOKIE,
        slug,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        path="/",
    )


def _query_except_region() -> str:
    if not request.args:
        return ""
    parts = []
    for k, v in request.args.items(multi=True):
        if k in ("stay", "no_region", "cc", "hl"):
            continue
        parts.append(f"{k}={v}")
    return ("?" + "&".join(parts)) if parts else ""


_MARKETING_PATHS = {
    "": "home",
    "primitives": "primitives",
    "templates": "templates",
    "pricing": "pricing",
    "download": "download",
    "how-it-works": "how_it_works",
    "compositions": "compositions",
    "security": "security",
    "connections": "connections",
    "customers": "customers",
    "contact": "contact",
    "extend": "extend",
    "docs": "docs",
    "blog": "blog",
    "changelog": "changelog",
    "about": "about",
    "community": "community",
    "product": "product",
    "hardware": "hardware",
    "translate": "translate",
}


def register_marketing_regions(app: Flask, marketing_handlers: dict[str, Callable]) -> None:
    """Register /choose-region, market-prefixed marketing routes, and region gate."""

    @app.before_request
    def _marketing_region_apply():
        slug = market_from_path(request.path)
        if slug:
            apply_market_language(slug)
        return None

    @app.before_request
    def _marketing_region_gate():
        if request.method != "GET":
            return None
        path = request.path or "/"
        if path.startswith("/static/") or path.startswith("/api/"):
            return None
        if market_from_path(path):
            return None
        if path == "/choose-region" or path.startswith("/choose-region/"):
            return None
        if path != "/":
            return None
        if request.args.get("legacy") == "1":
            return None
        if request.args.get("stay") == "1" or request.args.get("no_region") == "1":
            return None
        chosen = request.cookies.get(MARKET_CHOICE_COOKIE) or session.get("market_chosen")
        if chosen:
            if chosen == INTL_SLUG or chosen in ("global",):
                return None
            normalized = _normalize_market_slug(str(chosen))
            if normalized:
                if normalized != chosen:
                    resp = redirect(f"/{normalized}{_query_except_region()}")
                    _persist_market_choice(normalized, resp)
                    return resp
                return redirect(f"/{normalized}{_query_except_region()}")
            # Stale cookie — fall through to detect again.
        detected = detect_market_slug()
        if detected:
            resp = redirect(f"/{detected}{_query_except_region()}")
            _persist_market_choice(detected, resp)
            return resp
        return redirect(url_for("marketing_choose_region"))

    @app.get("/choose-region")
    def marketing_choose_region():
        detected_markets = markets_for_detected_country()
        return render_template(
            "marketing/choose_region.html",
            groups=market_groups_for_picker(),
            detected=detect_market_slug(),
            detected_markets=detected_markets,
            region_label=region_display_name,
        )

    @app.get("/choose-region/<slug>")
    def marketing_choose_region_go(slug: str):
        slug = slug.lower().strip()
        if slug in (INTL_SLUG, "global"):
            # stay=1 skips geo auto-route on the next hop if cookies lag
            q = _query_except_region()  # "" or "?a=1"
            if q.startswith("?"):
                dest = f"/{q}&stay=1"
            else:
                dest = "/?stay=1"
            resp = redirect(dest)
            _persist_market_choice(INTL_SLUG, resp)
            return resp
        if slug not in MARKET_SLUGS:
            return redirect(url_for("marketing_choose_region"))
        resp = redirect(f"/{slug}{_query_except_region()}")
        _persist_market_choice(slug, resp)
        return resp

    def _dispatch_market(slug: str, rest: str = ""):
        if slug not in MARKET_SLUGS:
            abort(404)
        apply_market_language(slug)
        rest = (rest or "").strip("/")
        if rest.startswith("compositions/") and marketing_handlers.get("composition_detail"):
            detail = rest.split("/", 1)[1]
            return marketing_handlers["composition_detail"](detail)
        if rest.startswith("blog/") and marketing_handlers.get("blog_post"):
            detail = rest.split("/", 1)[1]
            return marketing_handlers["blog_post"](detail)
        if rest.startswith("compare/") and marketing_handlers.get("compare"):
            detail = rest.split("/", 1)[1]
            return marketing_handlers["compare"](detail)
        key = _MARKETING_PATHS.get(rest)
        if not key:
            abort(404)
        handler = marketing_handlers.get(key)
        if not handler:
            abort(404)
        return handler()

    @app.route("/<slug>", methods=["GET"])
    @app.route("/<slug>/", methods=["GET"])
    def market_home(slug: str):
        if slug in RESERVED_ROOT_SEGMENTS:
            abort(404)
        legacy = LEGACY_SLUG_REDIRECTS.get(slug)
        if legacy and legacy != slug:
            return redirect(f"/{legacy}{_query_except_region()}", code=301)
        if slug not in MARKET_SLUGS:
            abort(404)
        return _dispatch_market(slug, "")

    @app.route("/<slug>/<path:rest>", methods=["GET", "POST"])
    def market_subpage(slug: str, rest: str):
        if slug in RESERVED_ROOT_SEGMENTS:
            abort(404)
        legacy = LEGACY_SLUG_REDIRECTS.get(slug)
        if legacy and legacy != slug:
            suffix = (rest or "").strip("/")
            target = f"/{legacy}/{suffix}" if suffix else f"/{legacy}"
            return redirect(target + _query_except_region(), code=301)
        if slug not in MARKET_SLUGS:
            abort(404)
        # Only contact accepts POST under market prefix.
        if request.method == "POST" and rest.strip("/") != "contact":
            abort(405)
        return _dispatch_market(slug, rest)

    @app.context_processor
    def inject_market():
        slug = getattr(g, "market_slug", None)

        def murl(path: str = "/") -> str:
            return url_for_marketing_path(path)

        return {
            "market_slug": slug,
            "market_prefix": market_prefix(slug),
            "market_meta": getattr(g, "market", None),
            "region_label": region_display_name,
            "murl": murl,
            "region_mismatch": region_mismatch_hint(),
        }
