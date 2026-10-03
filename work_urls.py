"""Canonical URLs for a published work (storefront or Builder site).

Custom domains should later change only work_base_path().
"""

from __future__ import annotations

from typing import Any, Mapping

from flask import abort, g, has_request_context, request


def work_dict(*, kind: str, slug: str, **extra: Any) -> dict[str, Any]:
    kind = "store" if kind == "store" else "build"
    data = {"kind": kind, "slug": str(slug or "").strip()}
    data.update(extra)
    return data


def work_base_path(work: Mapping[str, Any] | None) -> str:
    if not work:
        return ""
    slug = str(work.get("slug") or work.get("store_slug") or work.get("project_slug") or "").strip()
    if not slug:
        return ""
    kind = work.get("kind") or ("store" if work.get("store_id") or work.get("store") else "build")
    prefix = "store" if kind == "store" else "build"
    return f"/{prefix}/{slug}"


def work_url(work: Mapping[str, Any] | None, rest: str = "account") -> str:
    base = work_base_path(work)
    piece = (rest or "").strip("/")
    if not base:
        return f"/{piece}" if piece else "/"
    return f"{base}/{piece}" if piece else base


def parse_work_from_path(path: str) -> tuple[str, str] | None:
    parts = [p for p in (path or "").split("/") if p]
    if len(parts) < 3:
        return None
    if parts[0] not in {"store", "build"}:
        return None
    if parts[2] != "account" and not (len(parts) >= 2 and parts[0] in {"store", "build"}):
        pass
    return parts[0], parts[1]


def parse_work_account_from_path(path: str) -> tuple[str, str, str] | None:
    """Return (kind, slug, rest) when path is /store|build/<slug>/account[...]."""
    parts = [p for p in (path or "").split("/") if p]
    if len(parts) < 3 or parts[0] not in {"store", "build"} or parts[2] != "account":
        return None
    rest = "/".join(parts[3:])
    return parts[0], parts[1], rest


def rewrite_account_href(href: str, work: Mapping[str, Any] | None) -> str:
    raw = (href or "").strip()
    if not raw or not work:
        return raw
    if raw.startswith("/account/") or raw == "/account":
        rest = raw[1:] if raw.startswith("/") else raw
        return work_url(work, rest)
    if raw.startswith("account/") or raw == "account":
        return work_url(work, raw)
    return raw


def current_work():
    if has_request_context():
        return getattr(g, "work", None)
    return None


def resolve_work_or_404(kind: str, slug: str) -> dict[str, Any]:
    slug = (slug or "").strip()
    if not slug:
        abort(404)
    if kind == "store":
        from app import public_store_or_404

        store = public_store_or_404(slug)
        return work_dict(kind="store", slug=store["slug"], store=store, store_id=store["id"])
    from app import db

    with db() as conn:
        row = conn.execute(
            "SELECT id, slug, workspace_id, status FROM builder_projects WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not row:
            abort(404)
        store = conn.execute(
            "SELECT id, slug FROM stores WHERE workspace_id = ? ORDER BY id LIMIT 1",
            (row["workspace_id"],),
        ).fetchone()
    if store:
        return work_dict(
            kind="store",
            slug=store["slug"],
            store_id=store["id"],
            project_id=row["id"],
            project_slug=row["slug"],
        )
    return work_dict(kind="build", slug=row["slug"], project_id=row["id"])


def work_from_store(store: Mapping[str, Any]) -> dict[str, Any]:
    slug = store["slug"]
    store_id = store["id"] if "id" in store.keys() else None
    return work_dict(kind="store", slug=slug, store=store, store_id=store_id)


def inject_work_globals():
    work = current_work()
    return {
        "current_work": work,
        "work_url": (lambda rest="account": work_url(work, rest)) if work else work_url,
        "work_base_path": work_base_path(work) if work else "",
    }
