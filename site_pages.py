"""Public marketing pages, region routing, and site-wide template globals."""

from __future__ import annotations

import os
import re
from datetime import datetime

from flask import abort, jsonify, render_template, request
from markupsafe import Markup, escape

from marketing_regions import register_marketing_regions
from marketing_site import compare_by_slug, localized_changelog
from site_seo import register_site_seo

_BOLD = re.compile(r"\*\*(.+?)\*\*")

_PLATFORM_ENV = (
    ("mac", "STUDIO_DOWNLOAD_MAC_URL"),
    ("win", "STUDIO_DOWNLOAD_WIN_URL"),
    ("linux", "STUDIO_DOWNLOAD_LINUX_URL"),
)


def rich(value) -> Markup:
    text = str(escape(value or ""))
    return Markup(_BOLD.sub(r"<strong>\1</strong>", text))


def installer_available() -> bool:
    return any((os.environ.get(env) or "").strip() for _pid, env in _PLATFORM_ENV)


def download_platforms() -> list[dict]:
    rows = []
    for pid, env in _PLATFORM_ENV:
        url = (os.environ.get(env) or "").strip()
        prefix = {
            "mac": "STUDIO_MAC",
            "win": "STUDIO_WIN",
            "linux": "STUDIO_LINUX",
        }[pid]
        rows.append(
            {
                "id": pid,
                "ready": bool(url),
                "url": url,
                "min": (os.environ.get("STUDIO_MAC_MIN") or "").strip() if pid == "mac" else "",
                "version": (os.environ.get(f"{prefix}_VERSION") or "").strip(),
                "date": (os.environ.get(f"{prefix}_DATE") or "").strip(),
                "size": (os.environ.get(f"{prefix}_SIZE") or "").strip(),
                "checksum": (os.environ.get(f"{prefix}_CHECKSUM") or "").strip(),
            }
        )
    return rows


def _notice_from_form(*, default_kind: str):
    from app import db
    from site_notices import submit_notice, submit_platform_notices

    kind = (request.form.get("kind") or default_kind).strip()
    email = request.form.get("email") or ""
    ip = request.remote_addr or ""
    with db() as conn:
        if kind == "platform_notify":
            platforms = request.form.getlist("platform")
            return submit_platform_notices(conn, email=email, platforms=platforms, ip=ip)
        return submit_notice(
            conn,
            kind=kind,
            email=email,
            platform=request.form.get("platform") or "",
            note=request.form.get("use") or request.form.get("note") or "",
            region=request.form.get("region") or "",
            ip=ip,
        )


def register_site_pages(app) -> None:
    app.add_template_filter(rich, name="rich")
    app.jinja_env.globals["rich"] = rich

    @app.context_processor
    def inject_site_pages():
        from site_config import CONTACT_EMAIL
        from site_notices import mail_configured
        from site_theme import public_theme_attrs

        args = request.args if request else {}
        return {
            **public_theme_attrs(),
            "current_year": datetime.now().year,
            "installer_available": installer_available(),
            "download_ready": {item["id"]: bool(item["ready"]) for item in download_platforms()},
            "contact_email": CONTACT_EMAIL,
            "mail_configured": mail_configured(),
            "auth_next": (args.get("next") or "") if args is not None else "",
            "pending_package": (args.get("package") or "") if args is not None else "",
            "preferred_template": (args.get("template") or None) if args is not None else None,
        }

    def marketing_home():
        ready = {item["id"]: bool(item["ready"]) for item in download_platforms()}
        return render_template("marketing/home.html", download_ready=ready)

    def marketing_product():
        return render_template("marketing/product.html")

    def marketing_pricing():
        return render_template("marketing/pricing.html")

    def marketing_docs():
        return render_template("marketing/docs.html")

    def marketing_plugins():
        from plugin_catalog import catalog

        return render_template("marketing/plugins.html", plugin_packs=catalog(include_pending=False))

    def plugins_file(filename: str):
        from flask import Response
        from plugin_catalog import official_pack_file

        pack = official_pack_file(filename)
        if not pack:
            abort(404)
        resp = jsonify(pack)
        resp.headers["Content-Disposition"] = f'attachment; filename="{pack["file"]}"'
        return resp

    def plugins_catalog_json():
        from plugin_catalog import hosted_catalog

        return jsonify(hosted_catalog())

    def marketing_security():
        return render_template("marketing/security.html")

    def marketing_about():
        return render_template("marketing/about.html")

    def marketing_changelog():
        return render_template("marketing/changelog.html", entries=localized_changelog())

    def marketing_translate():
        from i18n_platform import core_coverage, get_active_language

        percent = int(round(core_coverage(get_active_language()) * 100))
        return render_template("marketing/translate.html", translate_percent=percent)

    def marketing_compare(slug: str):
        page = compare_by_slug(slug)
        if not page:
            abort(404)
        return render_template("marketing/compare.html", page=page)

    def marketing_download():
        from site_notices import mail_configured

        notice = None
        if request.method == "POST" and mail_configured():
            notice = _notice_from_form(default_kind="download_link")
        started = (request.args.get("started") or request.args.get("pending") or "").strip().lower()
        if started not in {"mac", "win", "linux"}:
            started = ""
        return render_template(
            "marketing/download.html",
            platforms=download_platforms(),
            notice=notice,
            started=started,
            mail_configured=mail_configured(),
        )

    def marketing_hardware():
        from site_notices import mail_configured

        notice = None
        if request.method == "POST" and mail_configured():
            notice = _notice_from_form(default_kind="hardware_wait")
        return render_template(
            "marketing/hardware.html",
            notice=notice,
            mail_configured=mail_configured(),
        )

    def marketing_contact():
        from email_delivery import send_transactional_email
        from site_config import CONTACT_EMAIL
        from site_notices import mail_configured

        sent = False
        if request.method == "POST" and mail_configured():
            topic = (request.form.get("topic") or "").strip()
            name = (request.form.get("name") or "").strip()
            email = (request.form.get("email") or "").strip()
            message = (request.form.get("message") or "").strip()
            body = f"Topic: {topic}\nName: {name}\nFrom: {email}\n\n{message}"
            send_transactional_email(CONTACT_EMAIL, f"Zintriq contact: {topic or 'message'}", body)
            sent = True
        return render_template(
            "marketing/contact.html",
            sent=sent,
            mail_configured=mail_configured(),
            contact_email=CONTACT_EMAIL,
        )

    def site_notice_unsubscribe(token: str):
        from app import db
        from site_notices import unsubscribe_notice

        with db() as conn:
            removed = unsubscribe_notice(conn, token)
        return render_template("marketing/unsubscribed.html", removed=removed)

    app.add_url_rule("/product", endpoint="marketing_product", view_func=marketing_product, methods=["GET"])
    app.add_url_rule("/pricing", endpoint="marketing_pricing", view_func=marketing_pricing, methods=["GET"])
    app.add_url_rule("/docs", endpoint="marketing_docs", view_func=marketing_docs, methods=["GET"])
    app.add_url_rule("/plugins", endpoint="marketing_plugins", view_func=marketing_plugins, methods=["GET"])
    app.add_url_rule("/plugins/files/<filename>", endpoint="plugins_file", view_func=plugins_file, methods=["GET"])
    app.add_url_rule(
        "/plugins/catalog.json",
        endpoint="plugins_catalog_json",
        view_func=plugins_catalog_json,
        methods=["GET"],
    )
    app.add_url_rule("/security", endpoint="marketing_security", view_func=marketing_security, methods=["GET"])
    app.add_url_rule("/about", endpoint="marketing_about", view_func=marketing_about, methods=["GET"])
    app.add_url_rule("/changelog", endpoint="marketing_changelog", view_func=marketing_changelog, methods=["GET"])
    app.add_url_rule("/translate", endpoint="marketing_translate", view_func=marketing_translate, methods=["GET"])
    app.add_url_rule("/compare/<slug>", endpoint="marketing_compare", view_func=marketing_compare, methods=["GET"])
    app.add_url_rule(
        "/download",
        endpoint="marketing_download",
        view_func=marketing_download,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/hardware",
        endpoint="marketing_hardware",
        view_func=marketing_hardware,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/contact",
        endpoint="marketing_contact",
        view_func=marketing_contact,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/notify/unsubscribe/<token>",
        endpoint="site_notice_unsubscribe",
        view_func=site_notice_unsubscribe,
        methods=["GET"],
    )

    register_marketing_regions(
        app,
        {
            "home": marketing_home,
            "product": marketing_product,
            "pricing": marketing_pricing,
            "docs": marketing_docs,
            "plugins": marketing_plugins,
            "security": marketing_security,
            "about": marketing_about,
            "changelog": marketing_changelog,
            "translate": marketing_translate,
            "download": marketing_download,
            "hardware": marketing_hardware,
            "contact": marketing_contact,
            "compare": marketing_compare,
        },
    )
    def design_lab():
        if not app.debug:
            abort(404)
        return render_template("marketing/design.html")

    app.add_url_rule("/__design", endpoint="design_lab", view_func=design_lab, methods=["GET"])

    register_site_seo(app)
    from billing_platform import register_billing

    register_billing(app)
