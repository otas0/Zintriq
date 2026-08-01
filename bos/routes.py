"""Business OS API and page routes."""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from bos.models import BOS_MODULES, module_for_id

bos_bp = Blueprint("bos", __name__, url_prefix="/app")


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
    return {"bos_modules": BOS_MODULES}


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


@bos_bp.get("")
@_login_required
def home():
    return _render_module("home", "Home", "Your Business OS overview")


@bos_bp.get("/organizations")
@_login_required
def organizations():
    return _render_module("organizations", "Organization", "Manage your company profile")


@bos_bp.get("/workspaces")
@_login_required
def workspaces():
    return _render_module("workspaces", "Workspaces", "Business units and locations")


@bos_bp.get("/catalog")
@_login_required
def catalog():
    return _render_module("catalog", "Catalog", "Products and services")


@bos_bp.get("/transactions")
@_login_required
def transactions():
    return _render_module("transactions", "Transactions", "Sales and payments")


@bos_bp.get("/customers")
@_login_required
def customers():
    return _render_module("customers", "Customers", "Contacts and relationships")


@bos_bp.get("/team")
@_login_required
def team():
    return _render_module("team", "Team", "Members and roles")


@bos_bp.get("/assets")
@_login_required
def assets():
    return _render_module("assets", "Assets", "QR codes, storefronts, and resources")


@bos_bp.get("/operations")
@_login_required
def operations():
    return _render_module("operations", "Operations", "Tasks and workflows")


@bos_bp.get("/documents")
@_login_required
def documents():
    return _render_module("documents", "Documents", "Files and records")


@bos_bp.get("/tags")
@_login_required
def tags():
    return _render_module("tags", "Tags", "Labels and classification")


@bos_bp.get("/legacy/stores")
@_login_required
def legacy_stores_redirect():
    return redirect(url_for("my_stores"))
