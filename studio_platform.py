"""Zintriq Studio surface — desktop meta factory.

Web owns: marketing, download, published runtimes, account UX.
Studio (desktop) owns: describe, simulate, instantiate, space, and boundary
(a boundary is itself describable and buildable), plus Community.
Same existing Flask account as the website. Desktop signs in via /desktop/authorize (PKCE), not Auth0.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

from flask import abort, g, jsonify, redirect, render_template, request, session, url_for

_log = logging.getLogger("app.studio")

# Product surfaces (contracts — not modules)
SURFACE_WEB = "web"
SURFACE_STUDIO = "studio"
SURFACE_COMMUNITY = "community"

PRIMITIVES = ("describe", "simulate", "instantiate", "boundary", "space")

DEFAULT_DEEP_LINK_SCHEME = "zintriq"

STUDIO_TOKEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT 'Studio',
    prefix TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT '["studio"]',
    last_used_at TEXT,
    expires_at TEXT,
    revoked_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_studio_api_tokens_user ON studio_api_tokens(user_id);
"""


def deep_link_scheme() -> str:
    return (os.environ.get("STUDIO_DEEP_LINK_SCHEME") or DEFAULT_DEEP_LINK_SCHEME).strip() or DEFAULT_DEEP_LINK_SCHEME


def community_path(package_id: str | None = None) -> str:
    if package_id:
        return f"/app/community?{urlencode({'package': package_id})}"
    return "/app/community"


def studio_home_path(install: str | None = None) -> str:
    if install:
        return f"/studio?{urlencode({'install': install})}"
    return "/studio"


def studio_project_path(project_id: int) -> str:
    return "/studio/meta"


def studio_deep_link(*, action: str = "open", package_id: str | None = None, project_id: int | None = None) -> str:
    q: dict[str, str] = {"action": action}
    if package_id:
        q["package"] = package_id
    if project_id is not None:
        q["project"] = str(int(project_id))
    return f"{deep_link_scheme()}://studio?{urlencode(q)}"


def handoff_payload(*, package_id: str | None = None, project_id: int | None = None) -> dict:
    """URLs for Community ↔ Studio handoff inside the desktop app."""
    install = (package_id or "").strip() or None
    return {
        "surface_web": SURFACE_WEB,
        "surface_studio": SURFACE_STUDIO,
        "surface_community": SURFACE_COMMUNITY,
        "community_url": community_path(install),
        "studio_url": studio_project_path(project_id) if project_id else studio_home_path(install),
        "deep_link": studio_deep_link(action="install" if install else "open", package_id=install, project_id=project_id),
        "primitives": list(PRIMITIVES),
        "note": "Describe, simulate, and instantiate any meta object, including a boundary. Creators only.",
    }


def init_studio_tables(conn) -> None:
    conn.executescript(STUDIO_TOKEN_SCHEMA)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_studio_token(conn, user_id: int, *, name: str = "Studio", days: int = 90) -> tuple[str, dict]:
    raw = f"zst_{secrets.token_urlsafe(32)}"
    prefix = raw[:10]
    expires = (datetime.utcnow() + timedelta(days=max(1, min(days, 365)))).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """INSERT INTO studio_api_tokens (user_id, token_hash, name, prefix, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (int(user_id), _hash_token(raw), (name or "Studio")[:80], prefix, expires),
    )
    meta = {
        "id": int(cur.lastrowid),
        "name": (name or "Studio")[:80],
        "prefix": prefix,
        "expires_at": expires,
    }
    return raw, meta


def revoke_studio_token(conn, user_id: int, token_id: int) -> bool:
    cur = conn.execute(
        """UPDATE studio_api_tokens SET revoked_at=CURRENT_TIMESTAMP
           WHERE id=? AND user_id=? AND revoked_at IS NULL""",
        (int(token_id), int(user_id)),
    )
    return cur.rowcount > 0


def lookup_studio_token_user(conn, raw_token: str):
    token = (raw_token or "").strip()
    if not token.startswith("zst_"):
        return None
    row = conn.execute(
        """SELECT t.id AS token_id, t.user_id, u.email, u.account_kind
           FROM studio_api_tokens t
           JOIN users u ON u.id = t.user_id
           WHERE t.token_hash=? AND t.revoked_at IS NULL
             AND (t.expires_at IS NULL OR t.expires_at > CURRENT_TIMESTAMP)""",
        (_hash_token(token),),
    ).fetchone()
    if not row:
        return None
    conn.execute(
        "UPDATE studio_api_tokens SET last_used_at=CURRENT_TIMESTAMP WHERE id=?",
        (row["token_id"],),
    )
    return {"id": int(row["user_id"]), "email": row["email"], "auth": "studio_token"}


def extract_bearer_token() -> str | None:
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return (request.headers.get("X-Studio-Token") or "").strip() or None


def load_studio_bearer_user() -> None:
    """before_request: resolve Bearer studio token into g.studio_bearer_user."""
    g.studio_bearer_user = None
    raw = extract_bearer_token()
    if not raw:
        return
    from app import db
    from customer_account_platform import is_shopper_only_user

    with db() as conn:
        user = lookup_studio_token_user(conn, raw)
        if not user:
            return
        row = conn.execute("SELECT id, email, account_kind FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or is_shopper_only_user(conn, row):
            return
        g.studio_bearer_user = {"id": int(row["id"]), "email": row["email"], "auth": "studio_token"}


def request_has_studio_bearer() -> bool:
    return bool(getattr(g, "studio_bearer_user", None))


def studio_login_required(view):
    """Like login_required but accepts Studio Bearer tokens (JSON 401, no HTML redirect)."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        from app import current_user

        user = current_user()
        if not user:
            if request_has_studio_bearer() or request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def register_studio_platform(app) -> None:
    from app import current_user, db, login_required

    @app.get("/studio/desktop")
    def studio_desktop_gate():
        """Public Electron entry — Auth0 Native PKCE, no session cookie required."""
        user = current_user()
        if user:
            from desktop.server_mode import desktop_enabled

            if desktop_enabled():
                return redirect(studio_home_path())
            return redirect(url_for("account"))
        return render_template("studio/desktop_gate.html")

    @app.get("/studio")
    @login_required
    def studio_home():
        from desktop.server_mode import desktop_enabled
        from flask import abort

        if not desktop_enabled():
            abort(404)
        from desktop.meta_store import MetaStoreError, current_draft_slug, data_dir, studio_index
        from plugin_catalog import catalog, installed_index, pack_view_id, plugin_drafts, primary_installed_pack, unlocked_editor_views

        index = studio_index()
        fill_pack = ""
        fill_label = "Fill"
        fill_pane = ""
        try:
            root = data_dir()
            have = set(installed_index(root))
            bound = plugin_drafts(root)
            installed_packs = []
            for pack in catalog(include_pending=False, data_root=root):
                if pack.get("id") not in have:
                    continue
                row = dict(pack)
                row["draft_slug"] = bound.get(str(pack.get("id") or "")) or ""
                installed_packs.append(row)
            editor_views = unlocked_editor_views("describe", root)
            primary = primary_installed_pack(root)
            if primary:
                fill_pack = str(primary.get("id") or "")
                fill_label = "Fill from " + str(primary.get("name") or pack_view_id(primary) or "plugin")
                fill_pane = pack_view_id(primary) or ""
        except (MetaStoreError, OSError, TypeError, ValueError):
            installed_packs = []
            editor_views = []
        wanted_pane = str(request.args.get("pane") or "").strip()
        editor_ids = {item["id"] for item in editor_views}
        editor_pane = wanted_pane if wanted_pane in editor_ids else (editor_views[0]["id"] if editor_views else "")
        current_draft = str(request.args.get("draft") or "") or current_draft_slug() or ""
        return render_template(
            "studio/factory.html",
            page_title="Studio",
            studio_base="/studio",
            local_drafts=index["drafts"],
            local_artifacts=index["artifacts"],
            installed_packs=installed_packs,
            editor_views=editor_views,
            editor_pane=editor_pane,
            current_draft=current_draft,
            fill_pack=fill_pack,
            fill_label=fill_label,
            fill_pane=fill_pane,
        )

    @app.get("/account/workspaces")
    @login_required
    def account_workspaces():
        from desktop.server_mode import desktop_enabled
        from flask import abort

        if desktop_enabled():
            return studio_home()
        abort(404)

    @app.get("/studio/p/<int:project_id>")
    @login_required
    def studio_editor(project_id: int):
        from flask import abort

        from desktop.server_mode import desktop_enabled

        if desktop_enabled():
            return redirect("/studio")
        abort(404)

    def _render_meta_editor(slug: str | None, meta_view: str):
        from desktop.server_mode import desktop_enabled
        from flask import abort

        if not desktop_enabled():
            abort(404)
        from meta.description import to_json
        from meta.instantiation import default_site_desc

        initial_code = to_json(default_site_desc(), indent=2)
        initial_slug = slug or "site"
        initial_events = ""
        from desktop.meta_store import current_draft_slug, load_artifact, load_draft, save_draft, unused_slug
        from meta.instantiation import description_from_artifact

        view = str(meta_view or "describe").strip().lower()
        if view not in {"describe", "simulate", "instantiate", "space"}:
            view = "describe"
        qview = str(request.args.get("view") or "").strip().lower()
        if qview in {"describe", "simulate", "instantiate", "space"}:
            view = qview
        fresh = str(request.args.get("new") or "").strip().lower() in {"1", "true", "yes"}
        open_space = str(request.args.get("space") or "").strip().lower() in {"1", "true", "yes"}
        if open_space and view == "describe" and not slug:
            return redirect("/studio/space")
        if view == "space":
            from meta.boundary import space_desc

            initial_code = to_json(space_desc(), indent=2)
            initial_slug = "meta-space"
            try:
                draft = load_draft("meta-space")
                initial_code = draft["code"]
                initial_slug = draft.get("slug") or "meta-space"
                initial_events = draft.get("events") or ""
            except (OSError, ValueError, TypeError, KeyError):
                pass
        elif fresh and not slug:
            from plugin_catalog import default_new_code

            try:
                initial_slug = unused_slug()
            except (OSError, ValueError):
                initial_slug = "site"
            try:
                from desktop.meta_store import data_dir as meta_data_dir

                initial_code = default_new_code(meta_data_dir())
            except (OSError, TypeError, ValueError):
                initial_code = "{}"
            initial_events = ""
            try:
                save_draft(initial_slug, code=initial_code, current=True)
            except (OSError, ValueError, TypeError):
                pass
        else:
            load_slug = slug or current_draft_slug()
            if load_slug:
                try:
                    draft = load_draft(load_slug)
                    initial_code = draft["code"]
                    initial_slug = draft["slug"]
                    initial_events = draft["events"]
                except (OSError, ValueError):
                    if slug:
                        try:
                            artifact = load_artifact(slug)
                            initial_code = to_json(description_from_artifact(artifact), indent=2)
                            initial_slug = artifact.slug or slug
                        except (OSError, ValueError):
                            pass
        titles = {
            "describe": initial_slug or "Empty Space",
            "simulate": initial_slug or "Empty Space",
            "instantiate": initial_slug or "Empty Space",
            "space": initial_slug or "Empty Space",
        }
        from meta.editor_views import CORE_VIEW_IDS
        from meta.editor_views import list_views as list_editor_views
        from plugin_catalog import hardware_host_unlocked, unlocked_installs, view_unlocked

        from desktop.meta_store import MetaStoreError, data_dir

        editor_views = list_editor_views(view)
        try:
            installed = unlocked_installs(data_dir())
        except MetaStoreError:
            installed = []
        editor_views = [item for item in editor_views if view_unlocked(item["id"], installed)]
        wanted_pane = str(request.args.get("pane") or "").strip()
        editor_ids = [item["id"] for item in editor_views]
        editor_id_set = set(editor_ids)
        editor_pane = wanted_pane if wanted_pane in editor_id_set else (editor_views[0]["id"] if editor_views else "")

        return render_template(
            "studio/meta_editor.html",
            page_title=titles[view],
            studio_mode=True,
            studio_base="/studio",
            initial_code=initial_code,
            initial_slug=initial_slug,
            initial_events=initial_events,
            meta_view=view,
            meta_slug=initial_slug,
            workbench_surface=view,
            editor_views=editor_views,
            editor_ids=editor_ids,
            editor_pane=editor_pane,
            plugin_stage=bool(editor_id_set - CORE_VIEW_IDS),
            hardware_stage=hardware_host_unlocked(installed) and view == "instantiate",
        )

    @app.get("/studio/meta")
    @app.get("/studio/meta/<slug>")
    @login_required
    def studio_meta_editor(slug: str | None = None):
        return _render_meta_editor(slug, "describe")

    @app.get("/studio/simulate")
    @app.get("/studio/simulate/<slug>")
    @login_required
    def studio_meta_simulate(slug: str | None = None):
        return _render_meta_editor(slug, "simulate")

    @app.get("/studio/instantiate")
    @app.get("/studio/instantiate/<slug>")
    @login_required
    def studio_meta_instantiate(slug: str | None = None):
        return _render_meta_editor(slug, "instantiate")

    @app.get("/studio/space")
    @app.get("/studio/space/<slug>")
    @login_required
    def studio_meta_space(slug: str | None = None):
        return _render_meta_editor(slug, "space")

    @app.get("/app/community")
    @login_required
    def studio_community():
        """Community lives only in the desktop Studio shell — never on the public website."""
        from desktop.server_mode import desktop_enabled
        from flask import abort

        if not desktop_enabled():
            abort(404)
        pending = (request.args.get("open") or request.args.get("package") or "").strip()
        return render_template(
            "studio/community.html",
            page_title="Community",
            studio_base="/studio",
            pending_package=pending,
        )

    @app.get("/studio/settings")
    @login_required
    def studio_settings():
        from desktop.server_mode import desktop_enabled
        from flask import abort

        if not desktop_enabled():
            abort(404)
        return render_template(
            "studio/settings.html",
            page_title="Settings",
            studio_base="/studio",
            workbench_surface="settings",
        )

    @app.get("/api/studio/surfaces")
    def api_studio_surfaces():
        return jsonify(
            {
                "surfaces": {
                    SURFACE_WEB: {"owns": ["marketing", "download", "account", "published_runtimes"]},
                    SURFACE_COMMUNITY: {
                        "path": "/app/community",
                        "owns": ["discover", "import_handoff"],
                        "desktop_only": True,
                    },
                    SURFACE_STUDIO: {
                        "path": "/studio",
                        "owns": list(PRIMITIVES),
                        "deep_link_scheme": deep_link_scheme(),
                    },
                },
                "primitives": list(PRIMITIVES),
            }
        )

    @app.get("/api/studio/handoff")
    def api_studio_handoff():
        package_id = (request.args.get("package") or "").strip() or None
        project_raw = request.args.get("project")
        project_id = int(project_raw) if project_raw and str(project_raw).isdigit() else None
        return jsonify(handoff_payload(package_id=package_id, project_id=project_id))

    @app.get("/api/studio/me")
    def api_studio_me():
        user = current_user()
        if not user:
            return jsonify({"ok": False, "error": "Authentication required"}), 401
        return jsonify(
            {
                "ok": True,
                "user": {"id": user["id"], "email": user["email"]},
                "auth": user.get("auth") or ("studio_token" if request_has_studio_bearer() else "session"),
                "studio_home": studio_home_path(),
                "community_url": community_path(),
            }
        )

    @app.post("/api/studio/tokens")
    @login_required
    def api_studio_create_token():
        if request_has_studio_bearer():
            return jsonify({"ok": False, "error": "Create tokens from a browser session"}), 403
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "Studio").strip()[:80]
        days = int(data.get("days") or 90)
        user = current_user()
        with db() as conn:
            raw, meta = create_studio_token(conn, user["id"], name=name, days=days)
        _log.info("studio_token_created user_id=%s prefix=%s", user["id"], meta["prefix"])
        return jsonify({"ok": True, "token": raw, "token_meta": meta, "hint": "Store once — shown only now."})

    @app.get("/api/studio/tokens")
    @login_required
    def api_studio_list_tokens():
        user = current_user()
        with db() as conn:
            rows = conn.execute(
                """SELECT id, name, prefix, last_used_at, expires_at, created_at, revoked_at
                   FROM studio_api_tokens WHERE user_id=? ORDER BY id DESC""",
                (user["id"],),
            ).fetchall()
        return jsonify(
            {
                "tokens": [
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "prefix": r["prefix"],
                        "last_used_at": r["last_used_at"],
                        "expires_at": r["expires_at"],
                        "created_at": r["created_at"],
                        "revoked": bool(r["revoked_at"]),
                    }
                    for r in rows
                ]
            }
        )

    @app.delete("/api/studio/tokens/<int:token_id>")
    @login_required
    def api_studio_revoke_token(token_id: int):
        user = current_user()
        with db() as conn:
            ok = revoke_studio_token(conn, user["id"], token_id)
        if not ok:
            return jsonify({"ok": False, "error": "Token not found"}), 404
        return jsonify({"ok": True})

    @app.post("/api/studio/auth/pkce/exchange")
    def api_studio_pkce_exchange():
        """Retired Auth0 Native exchange. Desktop signs in at /desktop/authorize."""
        abort(404)

    @app.get("/api/studio/download/<platform>")
    def api_studio_download(platform: str):
        """Redirect to configured installer URLs for the marketing download page."""
        key = {
            "mac": "STUDIO_DOWNLOAD_MAC_URL",
            "macos": "STUDIO_DOWNLOAD_MAC_URL",
            "darwin": "STUDIO_DOWNLOAD_MAC_URL",
            "win": "STUDIO_DOWNLOAD_WIN_URL",
            "windows": "STUDIO_DOWNLOAD_WIN_URL",
            "linux": "STUDIO_DOWNLOAD_LINUX_URL",
        }.get((platform or "").strip().lower())
        if not key:
            return jsonify({"ok": False, "error": "Unknown platform"}), 404
        url = (os.environ.get(key) or "").strip()
        if not url:
            return redirect(url_for("marketing_download", pending=platform))
        return redirect(url)
