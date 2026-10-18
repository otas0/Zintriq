"""Zintriq API and page routes — MVP scope."""

from __future__ import annotations

from functools import wraps
import logging

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from bos.models import BOS_MODULES

_log = logging.getLogger("app.bos")

bos_bp = Blueprint("bos", __name__, url_prefix="/app")

# Platforms removed from MVP — redirect to Store
_V1_REMOVED = frozenset({
    "organizations", "catalog", "transactions", "contacts",
    "assets", "documents", "tags", "workspaces",
})


def _current_user():
    from app import current_user

    return current_user()


def _login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from flask import session

        from app import current_user
        from customer_account_platform import current_customer_id

        if current_customer_id(session) and not session.get("user_id"):
            flash("You're on a published app surface. Sign in to Zintriq to open Builder.", "error")
            return redirect(url_for("login"))
        if not current_user():
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@bos_bp.app_context_processor
def inject_bos_modules():
    from flask import session
    from app import db

    ws_id = session.get("active_workspace_id")
    ws_name = ""
    if ws_id:
        try:
            with db() as conn:
                row = conn.execute("SELECT name FROM workspaces WHERE id=?", (int(ws_id),)).fetchone()
                ws_name = row["name"] if row else ""
        except (TypeError, ValueError):
            _log.debug("bos_ws_name_lookup_failed", exc_info=True, extra={"op": "inject_bos_modules"})
            pass
    return {
        "bos_modules": BOS_MODULES,
        "bos_active_workspace_id": ws_id,
        "bos_active_workspace_name": ws_name,
    }


def _redirect_removed():
    return redirect("/app/builder")


def _primary_store_slug(owner_id: int) -> str | None:
    from app import db

    with db() as conn:
        row = conn.execute(
            """
            SELECT slug FROM stores
            WHERE owner_id = ?
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT 1
            """,
            (owner_id,),
        ).fetchone()
    return row["slug"] if row else None


def _manage_hub_redirect(*, flash_message: str, manage_endpoint: str | None = None):
    """Send owners to live /manage/* when they have a store; otherwise Builder."""
    user = _current_user()
    if not user:
        return redirect(url_for("universal_builder_home"))
    slug = _primary_store_slug(user["id"])
    if slug:
        flash(flash_message, "info")
        if manage_endpoint:
            return redirect(url_for(manage_endpoint, slug=slug))
        return redirect(url_for("manage_store", slug=slug))
    flash(
        "Compose and publish a store surface first — live operations open under Manage.",
        "info",
    )
    return redirect(url_for("universal_builder_home"))


@bos_bp.get("")
@_login_required
def home():
    return redirect("/app/builder")


@bos_bp.get("/store")
@_login_required
def store():
    return _manage_hub_redirect(
        flash_message="Live store hub — products, QR, and storefront settings.",
    )


@bos_bp.get("/store/organize")
@_login_required
def store_organize():
    return redirect(url_for("store_groups_manage"))


@bos_bp.get("/responses")
@_login_required
def responses():
    return _manage_hub_redirect(
        flash_message="Customer requests and responses live in Manage.",
        manage_endpoint="manage_store_inquiries",
    )


@bos_bp.get("/customers")
@bos_bp.get("/interactions")
@bos_bp.get("/feedback")
@_login_required
def legacy_response_routes():
    return _manage_hub_redirect(
        flash_message="Customer responses live in Manage.",
        manage_endpoint="manage_store_inquiries",
    )


@bos_bp.get("/operations")
@_login_required
def operations():
    return _manage_hub_redirect(
        flash_message="Day-to-day operations open from your live store hub.",
    )


@bos_bp.get("/qr")
@_login_required
def qr_experiences():
    """Legacy QR Experiences URL — redirect into store Customer QR hub."""
    exp_id = (request.args.get("experience") or request.args.get("builder") or "").strip()
    if exp_id.isdigit():
        from app import db
        from customer_qr_platform import manage_landing_qr_href

        with db() as conn:
            href = manage_landing_qr_href(
                conn,
                int(exp_id),
                builder=bool(request.args.get("builder")),
            )
        return redirect(href)
    return _manage_hub_redirect(
        flash_message="Customer QR and experiences live in Manage.",
        manage_endpoint="manage_qr_hub",
    )


@bos_bp.get("/calendar")
@bos_bp.get("/booking")
@_login_required
def deferred_operations():
    return _manage_hub_redirect(
        flash_message="Calendar and booking tie into your published store — open Manage for live ops.",
    )


@bos_bp.get("/check-in")
@_login_required
def check_in():
    return _manage_hub_redirect(
        flash_message="Check-in points are managed on your live store.",
        manage_endpoint="manage_check_in",
    )


@bos_bp.get("/team")
@_login_required
def team():
    return redirect(url_for("account_workspaces") + "#team")


@bos_bp.get("/settings")
@_login_required
def settings():
    return redirect(url_for("account_workspaces"))


@bos_bp.get("/workspaces")
@_login_required
def workspaces():
    return redirect(url_for("account_workspaces"))


@bos_bp.get("/organizations")
@bos_bp.get("/catalog")
@bos_bp.get("/transactions")
@bos_bp.get("/contacts")
@bos_bp.get("/assets")
@bos_bp.get("/documents")
@bos_bp.get("/tags")
@_login_required
def removed_v1_modules():
    return _redirect_removed()


@bos_bp.get("/legacy/stores")
@_login_required
def legacy_stores_redirect():
    return redirect("/app/builder")
