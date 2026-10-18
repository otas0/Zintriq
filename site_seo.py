"""Public sitemap, robots.txt, and per-page SEO helpers."""

from __future__ import annotations

import os

from flask import Response, g, request

SITEMAP_PATHS = (
    "/",
    "/product",
    "/download",
    "/hardware",
    "/pricing",
    "/docs",
    "/security",
    "/about",
    "/contact",
    "/changelog",
    "/compare/site-builders",
    "/compare/low-code",
    "/translate",
    "/status",
    "/login",
    "/register",
    "/legal/privacy",
    "/legal/terms",
    "/legal/cookies",
    "/legal/imprint",
)

PATH_DESCRIPTION_KEYS = {
    "/": "home.hero.lead",
    "/product": "product.lead",
    "/download": "dl.lead",
    "/hardware": "hw.lead",
    "/pricing": "pricing.lead",
    "/docs": "docs.search",
    "/security": "sec.title",
    "/about": "about.body",
    "/contact": "contact.lead",
    "/changelog": "changelog.lead",
    "/translate": "translate.lead",
    "/status": "status.lead",
    "/login": "auth.login.title",
    "/register": "auth.signup.lead",
}

OG_LOCALES = {
    "en": "en_US",
    "zh-Hans": "zh_CN",
    "zh-Hant": "zh_TW",
}


def public_base() -> str:
    env = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    if request:
        return request.url_root.rstrip("/")
    return "https://zintriq.com"


def picker_codes() -> list[str]:
    from i18n_platform import language_options

    return [item["code"] for item in language_options()]


def page_url(path: str, lang: str | None = None) -> str:
    from i18n_platform import DEFAULT_LANGUAGE

    base = public_base()
    loc = base if path == "/" else f"{base}{path}"
    if lang and lang != DEFAULT_LANGUAGE:
        loc = f"{loc}?hl={lang}"
    return loc


def robots_indexable() -> bool:
    from i18n_platform import core_coverage, get_active_language
    from site_config import I18N_SELECTOR_COVERAGE

    code = get_active_language()
    return core_coverage(code) + 1e-9 >= I18N_SELECTOR_COVERAGE


def _current_path() -> str:
    path = request.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return path or "/"


def seo_description() -> str:
    from i18n_platform import translate as _

    path = _current_path()
    key = PATH_DESCRIPTION_KEYS.get(path)
    if key:
        return _(key)
    if path.startswith("/compare/"):
        from marketing_site import compare_by_slug

        page = compare_by_slug(path.rsplit("/", 1)[-1])
        if page:
            return page["lead"]
    return _("home.hero.lead")


def seo_context() -> dict:
    from i18n_platform import DEFAULT_LANGUAGE, get_active_language

    path = _current_path()
    lang = get_active_language()
    canonical = page_url(path, None if lang == DEFAULT_LANGUAGE else lang)
    hreflang = [("x-default", page_url(path, None))]
    for code in picker_codes():
        hreflang.append((code, page_url(path, None if code == DEFAULT_LANGUAGE else code)))
    return {
        "seo_canonical": canonical,
        "seo_hreflang": hreflang,
        "seo_description": seo_description(),
        "seo_noindex": not robots_indexable(),
        "seo_og_locale": OG_LOCALES.get(lang, lang.replace("-", "_")),
        "seo_og_url": canonical,
    }


def sitemap_xml() -> str:
    from i18n_platform import DEFAULT_LANGUAGE

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    langs = picker_codes() or [DEFAULT_LANGUAGE]
    for path in SITEMAP_PATHS:
        for lang in langs:
            loc = page_url(path, None if lang == DEFAULT_LANGUAGE else lang)
            lines.append("  <url>")
            lines.append(f"    <loc>{loc}</loc>")
            for code in langs:
                href = page_url(path, None if code == DEFAULT_LANGUAGE else code)
                lines.append(
                    f'    <xhtml:link rel="alternate" hreflang="{code}" href="{href}"/>'
                )
            lines.append(
                f'    <xhtml:link rel="alternate" hreflang="x-default" href="{page_url(path, None)}"/>'
            )
            lines.append("  </url>")
    try:
        from desktop_cloud import listed_share_paths

        extra = listed_share_paths()
    except Exception:
        extra = []
    for path in extra:
        loc = page_url(path, None)
        lines.append("  <url>")
        lines.append(f"    <loc>{loc}</loc>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt() -> str:
    base = public_base()
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /account\n"
        "Disallow: /api\n"
        "Disallow: /studio\n"
        "Disallow: /app\n"
        "Disallow: /locale\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


def register_site_seo(app) -> None:
    @app.context_processor
    def _seo_globals():
        if not request:
            return {}
        path = request.path or ""
        if path in ("/sitemap.xml", "/robots.txt"):
            return {}
        return seo_context()

    @app.get("/sitemap.xml")
    def sitemap():
        return Response(sitemap_xml(), mimetype="application/xml")

    @app.get("/robots.txt")
    def robots():
        return Response(robots_txt(), mimetype="text/plain")
