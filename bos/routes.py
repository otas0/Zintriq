"""Business OS API and page routes — MVP scope."""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from bos.models import BOS_MODULES, module_for_id

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
        if not _current_user():
            flash("Please sign in to manage a storefront.", "error")
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
            pass
    return {
        "bos_modules": BOS_MODULES,
        "bos_active_workspace_id": ws_id,
        "bos_active_workspace_name": ws_name,
    }


def _render_module(module_id: str, title: str, subtitle: str = ""):
    module = module_for_id(module_id)
    if not module:
        abort(404)
    return render_template(
        "bos/module.html",
        module_id=module_id,
        module=module,
        page_title=title,
        page_subtitle=subtitle,
    )


def _redirect_removed():
    return redirect(url_for("bos.store"))


@bos_bp.get("")
@_login_required
def home():
    return redirect(url_for("bos.store"))


@bos_bp.get("/store")
@_login_required
def store():
    from app import workspace_snapshot

    user = _current_user()
    return render_template(
        "bos/store_module.html",
        module_id="store",
        page_title="Stores",
        page_subtitle="Manage storefronts, customer QR, and responses.",
        workspace=workspace_snapshot(user["id"]),
        workspace_mode="all",
    )


@bos_bp.get("/store/organize")
@_login_required
def store_organize():
    from app import workspace_snapshot

    user = _current_user()
    return render_template(
        "bos/store_organize.html",
        module_id="store",
        page_title="Groups & labels",
        workspace=workspace_snapshot(user["id"]),
    )


@bos_bp.get("/responses")
@_login_required
def responses():
    return redirect(url_for("bos.store", _anchor="responses"))


@bos_bp.get("/customers")
@bos_bp.get("/interactions")
@bos_bp.get("/feedback")
@_login_required
def legacy_response_routes():
    return redirect(url_for("bos.store", _anchor="responses"))


@bos_bp.get("/operations")
@_login_required
def operations():
    return redirect(url_for("bos.store", _anchor="responses"))


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
    return redirect(url_for("bos.store", _anchor="experiences"))


@bos_bp.get("/calendar")
@bos_bp.get("/booking")
@bos_bp.get("/check-in")
@_login_required
def deferred_operations():
    return redirect(url_for("bos.store", _anchor="experiences"))


@bos_bp.get("/team")
@_login_required
def team():
    return _render_module("team", "Team", "Invite members and manage access")


@bos_bp.get("/settings")
@_login_required
def settings():
    return _render_module("settings", "Settings", "Workspace configuration")


@bos_bp.get("/workspaces")
@_login_required
def workspaces():
    return redirect(url_for("bos.settings"))


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
    return redirect(url_for("bos.store"))
