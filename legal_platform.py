"""Legal pages — Privacy, Terms, Cookies, Imprint."""

from __future__ import annotations

import os
from pathlib import Path

from flask import abort, render_template
from jinja2 import TemplateNotFound

LEGAL_DIR = Path(__file__).resolve().parent / "legal"
LEGAL_CONTACT_EMAIL = os.environ.get("LEGAL_CONTACT_EMAIL", "zintriq@gmail.com").strip()

PAGES = {
    "privacy": "privacy.html",
    "terms": "terms.html",
    "cookies": "cookies.html",
    "imprint": "imprint.html",
    "contact": "imprint.html",
}


def register_legal_platform(app) -> None:
    @app.context_processor
    def _legal_globals():
        return {
            "legal_contact_email": LEGAL_CONTACT_EMAIL,
        }

    def legal_page(page: str):
        key = (page or "").strip().lower().removesuffix(".html")
        filename = PAGES.get(key)
        if not filename:
            abort(404)
        try:
            return render_template(
                f"legal/{filename}",
                contact_email=LEGAL_CONTACT_EMAIL,
                legal_page=key if key != "contact" else "imprint",
            )
        except TemplateNotFound:
            abort(404)

    # Explicit endpoint name so url_for('legal_page', page=...) always resolves.
    app.add_url_rule(
        "/legal/<page>",
        endpoint="legal_page",
        view_func=legal_page,
        methods=["GET"],
    )
    app.add_url_rule(
        "/legal/<page>.html",
        endpoint="legal_page_html",
        view_func=legal_page,
        methods=["GET"],
    )
