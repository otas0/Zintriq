"""Stage 2 cloud drafts, publish, and /c/<id> trampoline. Not an editor."""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from typing import Any, Optional

from dataclasses import replace

from flask import Response, abort, jsonify, redirect, render_template, request, send_from_directory, url_for

from desktop.server_mode import desktop_enabled
from desktop_account import load_desktop_session
from meta.description.errors import DescriptionError
from meta.instantiation import InstantiationError, validate_slug

_CODE_MAX = 400_000
_TITLE_MAX = 120
_SHARE_RE = re.compile(r"^[a-z0-9]{8,24}$")
_UPDATE_FILE_RE = re.compile(
    r"^(latest(-mac|-linux)?(-arm64|-x64)?\.yml|[A-Za-z0-9._+-]+\.(dmg|zip|exe|AppImage|deb|blockmap))$"
)
_KIND_MAP = {
    "meta.system": "system",
    "system": "system",
    "meta.boundary": "boundary",
    "software.page": "page",
    "software.site": "site",
    "hardware.module": "hardware",
    "os.surface": "os",
    "meta.space": "space",
    "state_machine": "machine",
    "plugin": "plugin",
}


_ASSET_MAX = 256 * 1024
_ASSET_MAX_COUNT = 24
_ASSET_MIME = {
    "gif": "image/gif",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def reset_cloud_for_tests(conn) -> None:
    ensure_schema(conn)
    conn.execute("DELETE FROM desktop_share_assets")
    conn.execute("DELETE FROM desktop_cloud_drafts")
    conn.execute("DELETE FROM desktop_shares")
    conn.execute("DELETE FROM desktop_share_reports")
    conn.execute("DELETE FROM desktop_collab_docs")


def _ensure_column(conn, table: str, column: str, decl: str) -> None:
    cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_cloud_drafts (
            user_id INTEGER NOT NULL,
            slug TEXT NOT NULL,
            code TEXT NOT NULL,
            events TEXT,
            title TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, slug)
        )
        """
    )
    _ensure_column(conn, "desktop_cloud_drafts", "revision", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "desktop_cloud_drafts", "deleted_at", "TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_collab_docs (
            user_id INTEGER NOT NULL,
            slug TEXT NOT NULL,
            doc TEXT NOT NULL,
            clock TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, slug)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_shares (
            public_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            code TEXT NOT NULL,
            events TEXT,
            listed INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_share_assets (
            public_id TEXT NOT NULL,
            name TEXT NOT NULL,
            data BLOB NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (public_id, name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_share_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )


def listed_share_paths() -> list[str]:
    from app import db

    with db() as conn:
        ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT public_id, user_id FROM desktop_shares
            WHERE listed = 1 ORDER BY created_at DESC LIMIT 200
            """
        ).fetchall()
        paths = []
        for row in rows:
            if _owner_hosting_active(conn, int(row["user_id"])):
                paths.append(f"/c/{row['public_id']}")
    return paths


def register_desktop_cloud(app) -> None:
    @app.get("/api/desktop/cloud/entitlement")
    def cloud_entitlement():
        """Desktop reads Publish & sync gates via bearer session (not cookie /billing/status)."""
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(_entitlement_payload(int(user["user_id"])))

    @app.put("/api/desktop/cloud/drafts/<slug>")
    def cloud_put_draft(slug: str):
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        blocked = _subscription_block(int(user["user_id"]))
        if blocked is not None:
            return blocked
        try:
            clean = validate_slug(slug)
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        body = request.get_json(silent=True) or {}
        code = str(body.get("code") or "")
        if not code or len(code) > _CODE_MAX:
            return jsonify({"error": "invalid draft"}), 400
        events = str(body.get("events") or "")[:8000]
        title = str(body.get("title") or clean)[:_TITLE_MAX]
        updated = str(body.get("updated_at") or "")[:40] or _now()
        base_revision = body.get("base_revision")
        from app import db

        with db() as conn:
            ensure_schema(conn)
            existing = conn.execute(
                """
                SELECT revision, updated_at, title FROM desktop_cloud_drafts
                WHERE user_id = ? AND slug = ?
                """,
                (user["user_id"], clean),
            ).fetchone()
            if existing is not None and base_revision is not None:
                try:
                    wanted = int(base_revision)
                except (TypeError, ValueError):
                    return jsonify({"error": "invalid base_revision"}), 400
                current = int(existing["revision"] or 1)
                if wanted != current:
                    return jsonify(
                        {
                            "code": "conflict",
                            "error": "draft revision conflict",
                            "revision": current,
                            "title": existing["title"] or clean,
                            "updated_at": existing["updated_at"],
                        }
                    ), 409
            revision = int(existing["revision"] or 1) + 1 if existing is not None else 1
            conn.execute(
                """
                INSERT INTO desktop_cloud_drafts
                (user_id, slug, code, events, title, updated_at, revision, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(user_id, slug) DO UPDATE SET
                    code=excluded.code,
                    events=excluded.events,
                    title=excluded.title,
                    updated_at=excluded.updated_at,
                    revision=excluded.revision,
                    deleted_at=NULL
                """,
                (user["user_id"], clean, code, events, title, updated, revision),
            )
        return jsonify({"slug": clean, "updated_at": updated, "revision": revision, "ok": True})

    @app.delete("/api/desktop/cloud/drafts/<slug>")
    def cloud_delete_draft(slug: str):
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        blocked = _subscription_block(int(user["user_id"]))
        if blocked is not None:
            return blocked
        try:
            clean = validate_slug(slug)
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        from app import db

        with db() as conn:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT revision FROM desktop_cloud_drafts WHERE user_id = ? AND slug = ?",
                (user["user_id"], clean),
            ).fetchone()
            if row is None:
                return jsonify({"error": "not found"}), 404
            revision = int(row["revision"] or 1) + 1
            stamp = _now()
            conn.execute(
                """
                UPDATE desktop_cloud_drafts
                SET deleted_at = ?, updated_at = ?, revision = ?, code = '', events = ''
                WHERE user_id = ? AND slug = ?
                """,
                (stamp, stamp, revision, user["user_id"], clean),
            )
        return jsonify({"slug": clean, "deleted_at": stamp, "revision": revision, "ok": True})

    @app.get("/api/desktop/cloud/drafts")
    def cloud_list_drafts():
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        from app import db

        with db() as conn:
            ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT slug, title, updated_at, revision, deleted_at FROM desktop_cloud_drafts
                WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user["user_id"],),
            ).fetchall()
        return jsonify({
            "drafts": [
                {
                    "slug": row["slug"],
                    "title": row["title"],
                    "updated_at": row["updated_at"],
                    "revision": int(row["revision"] or 1),
                    "deleted_at": row["deleted_at"] or "",
                }
                for row in rows
            ]
        })

    @app.get("/api/desktop/cloud/drafts/<slug>")
    def cloud_get_draft(slug: str):
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        try:
            clean = validate_slug(slug)
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        from app import db

        with db() as conn:
            ensure_schema(conn)
            row = conn.execute(
                """
                SELECT slug, title, code, events, updated_at, revision, deleted_at
                FROM desktop_cloud_drafts
                WHERE user_id = ? AND slug = ?
                """,
                (user["user_id"], clean),
            ).fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(
            {
                "slug": row["slug"],
                "title": row["title"],
                "code": row["code"],
                "events": row["events"] or "",
                "updated_at": row["updated_at"],
                "revision": int(row["revision"] or 1),
                "deleted_at": row["deleted_at"] or "",
            }
        )

    @app.post("/api/desktop/cloud/publish")
    def cloud_publish():
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        blocked = _subscription_block(int(user["user_id"]))
        if blocked is not None:
            return blocked
        body = request.get_json(silent=True) or {}
        try:
            slug = validate_slug(str(body.get("slug") or ""))
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        from app import db

        with db() as conn:
            ensure_schema(conn)
            draft = conn.execute(
                "SELECT * FROM desktop_cloud_drafts WHERE user_id = ? AND slug = ?",
                (user["user_id"], slug),
            ).fetchone()
            if draft is None:
                return jsonify({"error": "save a draft first"}), 400
            code = str(draft["code"] or "")
            requested = str(body.get("title") or "").strip()
            title = requested[:_TITLE_MAX] if requested else _title_from_code(
                code,
                str(draft["title"] or slug),
            )
            kind = _kind_from_code(code)
            existing = conn.execute(
                """
                SELECT public_id FROM desktop_shares
                WHERE user_id = ? AND slug = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (user["user_id"], slug),
            ).fetchone()
            if existing is not None:
                public_id = existing["public_id"]
                conn.execute(
                    """
                    UPDATE desktop_shares
                    SET title = ?, kind = ?, code = ?, events = ?, listed = 1
                    WHERE public_id = ? AND user_id = ?
                    """,
                    (title, kind, code, draft["events"], public_id, user["user_id"]),
                )
            else:
                public_id = secrets.token_hex(6)
                conn.execute(
                    """
                    INSERT INTO desktop_shares
                    (public_id, user_id, slug, title, kind, code, events, listed, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        public_id,
                        user["user_id"],
                        slug,
                        title,
                        kind,
                        code,
                        draft["events"],
                        time.time(),
                    ),
                )
        return jsonify({
            "id": public_id,
            "url": f"/c/{public_id}",
            "work": f"/w/{public_id}",
            "open": f"zintriq://c/{public_id}",
        })

    @app.post("/api/desktop/cloud/publish-plugin")
    def cloud_publish_plugin():
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        blocked = _subscription_block(int(user["user_id"]))
        if blocked is not None:
            return blocked
        body = request.get_json(silent=True) or {}
        pack = body.get("pack") if isinstance(body.get("pack"), dict) else body
        if not isinstance(pack, dict) or not pack.get("id") or not pack.get("name"):
            return jsonify({"error": "plugin pack required"}), 400
        from plugin_catalog import PluginError, validate_manifest

        try:
            pack = validate_manifest(dict(pack))
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400
        code = json.dumps(pack, ensure_ascii=False)
        title = str(pack.get("name") or pack["id"])[:_TITLE_MAX]
        slug_src = str(pack.get("id") or "plugin").replace("_", "-")
        slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in slug_src.lower())[:40] or "plugin"
        from app import db

        with db() as conn:
            ensure_schema(conn)
            existing = conn.execute(
                """
                SELECT public_id FROM desktop_shares
                WHERE user_id = ? AND slug = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (user["user_id"], slug),
            ).fetchone()
            if existing is not None:
                public_id = existing["public_id"]
                conn.execute(
                    """
                    UPDATE desktop_shares
                    SET title = ?, kind = ?, code = ?, events = ?, listed = 1
                    WHERE public_id = ? AND user_id = ?
                    """,
                    (title, "plugin", code, "", public_id, user["user_id"]),
                )
            else:
                public_id = secrets.token_hex(6)
                conn.execute(
                    """
                    INSERT INTO desktop_shares
                    (public_id, user_id, slug, title, kind, code, events, listed, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (public_id, user["user_id"], slug, title, "plugin", code, "", time.time()),
                )
        return jsonify({
            "id": public_id,
            "kind": "plugin",
            "url": f"/c/{public_id}",
            "open": f"zintriq://c/{public_id}",
        })

    @app.post("/api/desktop/cloud/unpublish")
    def cloud_unpublish():
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        public_id = str(body.get("id") or "").strip().lower()
        if not _SHARE_RE.match(public_id):
            return jsonify({"error": "invalid share"}), 400
        from app import db

        with db() as conn:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT public_id FROM desktop_shares WHERE public_id = ? AND user_id = ?",
                (public_id, user["user_id"]),
            ).fetchone()
            if row is None:
                return jsonify({"error": "not found"}), 404
            conn.execute(
                "UPDATE desktop_shares SET listed = 0 WHERE public_id = ? AND user_id = ?",
                (public_id, user["user_id"]),
            )
        return jsonify({"ok": True, "id": public_id})

    @app.get("/api/desktop/cloud/catalog")
    def cloud_catalog():
        if desktop_enabled():
            abort(404)
        query = str(request.args.get("q") or "").strip().lower()
        kind_filter = str(request.args.get("type") or "").strip().lower()
        from app import db

        with db() as conn:
            ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT s.public_id, s.user_id, s.slug, s.title, s.kind, s.created_at, u.email
                FROM desktop_shares s
                JOIN users u ON u.id = s.user_id
                WHERE s.listed = 1
                ORDER BY s.created_at DESC
                LIMIT 200
                """
            ).fetchall()
            packages = []
            for row in rows:
                if not _owner_hosting_active(conn, int(row["user_id"])):
                    continue
                title = str(row["title"] or "")
                kind = _normalize_kind(row["kind"])
                hay = f"{title} {kind} {row['email']}".lower()
                if query and query not in hay:
                    continue
                if kind_filter and kind_filter != kind:
                    continue
                item = {
                    "id": row["public_id"],
                    "name": title,
                    "kind": kind,
                    "author": row["email"],
                    "publisher": row["email"],
                    "url": f"/c/{row['public_id']}",
                    "published_at": str(row["created_at"]),
                    "form": "plugin" if kind == "plugin" else kind,
                }
                packages.append(item)
        return jsonify({"packages": packages, "descriptions": packages, "count": len(packages)})

    @app.get("/api/desktop/cloud/mine")
    def cloud_mine():
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        from app import db

        with db() as conn:
            ensure_schema(conn)
            shares = conn.execute(
                """
                SELECT public_id, slug, title, kind, created_at
                FROM desktop_shares
                WHERE user_id = ? AND listed = 1
                ORDER BY created_at DESC
                """,
                (user["user_id"],),
            ).fetchall()
            drafts = conn.execute(
                """
                SELECT slug, title, updated_at FROM desktop_cloud_drafts
                WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user["user_id"],),
            ).fetchall()
        return jsonify({
            "shares": [
                {
                    "id": row["public_id"],
                    "name": row["title"],
                    "slug": row["slug"],
                    "kind": _normalize_kind(row["kind"]),
                    "url": f"/c/{row['public_id']}",
                    "author": "",
                }
                for row in shares
            ],
            "drafts": [dict(row) for row in drafts],
        })

    @app.get("/api/desktop/updates")
    def desktop_updates():
        if desktop_enabled():
            abort(404)
        version = (os.environ.get("STUDIO_LATEST_VERSION") or "0.1.0").strip() or "0.1.0"
        return jsonify(
            {
                "version": version,
                "name": "Zintriq Studio",
                "notes": "Signed builds install from File → Check for updates. Unsigned copies still use the download page.",
                "download": "/download",
                "feed": "/desktop/updates",
                "autoInstall": True,
            }
        )

    @app.get("/desktop/updates/<name>")
    def desktop_update_file(name: str):
        if desktop_enabled():
            abort(404)
        filename = os.path.basename(str(name or ""))
        if not _UPDATE_FILE_RE.match(filename):
            abort(404)
        root = (os.environ.get("STUDIO_UPDATE_DIR") or "").strip()
        if not root:
            abort(404)
        directory = os.path.abspath(root)
        target = os.path.abspath(os.path.join(directory, filename))
        if not target.startswith(directory + os.sep) and target != directory:
            abort(404)
        if not os.path.isfile(target):
            abort(404)
        return send_from_directory(directory, filename, as_attachment=False)

    @app.get("/api/desktop/cloud/shares/<public_id>")
    def cloud_get_share(public_id: str):
        if desktop_enabled():
            abort(404)
        share = _load_share(public_id)
        if share is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({
            "id": share["public_id"],
            "slug": share["slug"],
            "title": share["title"],
            "kind": share["kind"],
            "code": share["code"],
            "events": share["events"] or "",
            "author": share["email"],
        })

    @app.put("/api/desktop/cloud/shares/<public_id>/assets/<name>")
    def cloud_put_share_asset(public_id: str, name: str):
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        blocked = _subscription_block(int(user["user_id"]))
        if blocked is not None:
            return blocked
        key = str(public_id or "").strip().lower()
        if not _SHARE_RE.match(key):
            return jsonify({"error": "invalid share"}), 400
        from app import db

        with db() as conn:
            ensure_schema(conn)
            owned = conn.execute(
                "SELECT public_id FROM desktop_shares WHERE public_id = ? AND user_id = ?",
                (key, user["user_id"]),
            ).fetchone()
            if owned is None:
                return jsonify({"error": "not found"}), 404
            raw = request.get_data(cache=False) or b""
            try:
                clean, blob = _normalize_share_asset(name, raw)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM desktop_share_assets WHERE public_id = ?",
                (key,),
            ).fetchone()["n"]
            exists = conn.execute(
                "SELECT 1 FROM desktop_share_assets WHERE public_id = ? AND name = ?",
                (key, clean),
            ).fetchone()
            if exists is None and int(count or 0) >= _ASSET_MAX_COUNT:
                return jsonify({"error": "too many images"}), 400
            conn.execute(
                """
                INSERT INTO desktop_share_assets (public_id, name, data, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(public_id, name) DO UPDATE SET
                    data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (key, clean, blob, _now()),
            )
        return jsonify({"name": clean, "ok": True}), 201

    @app.get("/api/desktop/cloud/shares/<public_id>/assets")
    def cloud_list_share_assets(public_id: str):
        if desktop_enabled():
            abort(404)
        key = str(public_id or "").strip().lower()
        if not _SHARE_RE.match(key):
            return jsonify({"error": "invalid share"}), 400
        share = _load_share(key)
        if share is None:
            return jsonify({"error": "not found"}), 404
        from app import db

        with db() as conn:
            ensure_schema(conn)
            rows = conn.execute(
                "SELECT name FROM desktop_share_assets WHERE public_id = ? ORDER BY name",
                (key,),
            ).fetchall()
        return jsonify({"assets": [row["name"] for row in rows]})

    @app.get("/w/<public_id>/assets/<name>")
    def hosted_work_asset(public_id: str, name: str):
        if desktop_enabled():
            abort(404)
        share = _load_share(public_id)
        if share is None:
            abort(404)
        from meta.instantiation import validate_asset_name

        try:
            clean = validate_asset_name(name)
        except InstantiationError:
            abort(404)
        from app import db

        with db() as conn:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT data FROM desktop_share_assets WHERE public_id = ? AND name = ?",
                (share["public_id"], clean),
            ).fetchone()
        if row is None:
            abort(404)
        ext = clean.rsplit(".", 1)[-1].lower()
        response = Response(bytes(row["data"]), mimetype=_ASSET_MIME.get(ext, "application/octet-stream"))
        response.headers["Cache-Control"] = "public, max-age=300"
        return response

    @app.get("/c/<public_id>")
    def community_share(public_id: str):
        if desktop_enabled():
            abort(404)
        share = _load_share(public_id)
        if share is None:
            lapsed = _load_share(public_id, require_hosting=False)
            if lapsed is not None:
                return render_template(
                    "share.html",
                    share=None,
                    unpublished=True,
                    unpublished_title=lapsed.get("title") or "",
                ), 410
            return render_template("share.html", share=None), 404
        return render_template(
            "share.html",
            share=share,
            open_url=f"zintriq://c/{share['public_id']}",
            work_url=f"/w/{share['public_id']}",
        )

    @app.get("/w/<public_id>")
    @app.get("/w/<public_id>/<page_key>")
    def hosted_work(public_id: str, page_key: str | None = None):
        if desktop_enabled():
            abort(404)
        share = _load_share(public_id)
        if share is None:
            lapsed = _load_share(public_id, require_hosting=False)
            if lapsed is not None:
                return render_template(
                    "work.html",
                    share=None,
                    unpublished=True,
                    unpublished_title=lapsed.get("title") or "",
                ), 410
            return render_template("work.html", share=None), 404
        key = str(page_key or "").strip() or None
        if key in {"", "index", "home", "assets"}:
            key = None
        rendered = _hosted_html(share, page_key=key)
        if rendered:
            from builder_kernel.csp import BUILD_CSP

            response = Response(rendered, mimetype="text/html")
            response.headers["Content-Security-Policy"] = BUILD_CSP
            response.headers["Cache-Control"] = "public, max-age=60"
            return response
        return render_template(
            "work.html",
            share=share,
            open_url=f"zintriq://c/{share['public_id']}",
            download_url="/download",
        )

    @app.post("/c/<public_id>/report")
    def community_share_report(public_id: str):
        if desktop_enabled():
            abort(404)
        share = _load_share(public_id)
        if share is None:
            abort(404)
        reason = str(request.form.get("reason") or "other")[:80]
        from app import db

        with db() as conn:
            ensure_schema(conn)
            conn.execute(
                "INSERT INTO desktop_share_reports (public_id, reason, created_at) VALUES (?, ?, ?)",
                (share["public_id"], reason, time.time()),
            )
        return redirect(url_for("community_share", public_id=share["public_id"], reported=1))

    @app.get("/api/desktop/cloud/collab/<slug>")
    def cloud_get_collab(slug: str):
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        try:
            clean = validate_slug(slug)
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        from app import db

        with db() as conn:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT doc, clock FROM desktop_collab_docs WHERE user_id=? AND slug=?",
                (user["user_id"], clean),
            ).fetchone()
        if row is None:
            return jsonify({"slug": clean, "doc": None, "clock": {}})
        try:
            doc = json.loads(row["doc"])
            clock = json.loads(row["clock"])
        except json.JSONDecodeError:
            return jsonify({"slug": clean, "doc": None, "clock": {}})
        return jsonify({"slug": clean, "doc": doc, "clock": clock})

    @app.put("/api/desktop/cloud/collab/<slug>")
    def cloud_put_collab(slug: str):
        if desktop_enabled():
            abort(404)
        user = _require_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        try:
            clean = validate_slug(slug)
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        body = request.get_json(silent=True) or {}
        from meta.collab import merge, merge_clocks
        from app import db

        incoming_doc = body.get("doc")
        incoming_clock = body.get("clock") if isinstance(body.get("clock"), dict) else {}
        with db() as conn:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT doc, clock FROM desktop_collab_docs WHERE user_id=? AND slug=?",
                (user["user_id"], clean),
            ).fetchone()
            current_doc = None
            current_clock = {}
            if row is not None:
                try:
                    current_doc = json.loads(row["doc"])
                    current_clock = json.loads(row["clock"])
                except json.JSONDecodeError:
                    current_doc = None
            merged_doc = merge(current_doc, incoming_doc)
            clock = merge_clocks(current_clock, incoming_clock)
            payload = json.dumps(merged_doc) if merged_doc is not None else "null"
            conn.execute(
                """
                INSERT INTO desktop_collab_docs (user_id, slug, doc, clock, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, slug) DO UPDATE SET
                    doc=excluded.doc,
                    clock=excluded.clock,
                    updated_at=excluded.updated_at
                """,
                (user["user_id"], clean, payload, json.dumps(clock), _now()),
            )
        return jsonify({"slug": clean, "doc": merged_doc, "clock": clock, "ok": True})

    @app.get("/status")
    def marketing_status():
        if desktop_enabled():
            abort(404)
        return render_template("marketing/status.html")


def _require_user() -> Optional[dict[str, Any]]:
    return load_desktop_session()


def _entitlement_payload(user_id: int) -> dict[str, Any]:
    from billing_platform import (
        billing_checkout_ready,
        billing_enabled,
        ensure_schema as billing_schema,
        subscription_cloud_active,
        subscription_for_user,
        subscription_hosting_active,
    )
    from app import db

    with db() as conn:
        billing_schema(conn)
        row = subscription_for_user(conn, int(user_id))
        active = subscription_cloud_active(conn, int(user_id))
        hosting = subscription_hosting_active(conn, int(user_id))
    # Until BILLING_ENABLED, keep cloud APIs open so local/dev flows still publish.
    if not billing_enabled():
        active = True
        hosting = True
    return {
        "billing_enabled": billing_enabled(),
        "checkout_ready": billing_checkout_ready(),
        "cloud_active": bool(active),
        "cloud_data_until": (row or {}).get("cloud_data_until") or "",
        "hosting_active": bool(hosting),
        "hosting_until": (row or {}).get("hosting_until") or "",
        "local_export": True,
        "plan": (row or {}).get("plan") or "",
        "publish": bool(active),
        "status": (row or {}).get("status") or "",
        "sync": bool(active),
    }


def _subscription_block(user_id: int):
    """Return a Flask (response, status) tuple when Publish/sync must stop; else None."""
    from billing_platform import billing_enabled, ensure_schema as billing_schema, subscription_cloud_active
    from app import db

    if not billing_enabled():
        return None
    with db() as conn:
        billing_schema(conn)
        if subscription_cloud_active(conn, int(user_id)):
            return None
    return (
        jsonify(
            {
                "error": "Cloud subscription required for Publish & sync. Local export stays free.",
                "code": "subscription_required",
            }
        ),
        402,
    )


def _hosted_html(share: dict[str, Any], *, page_key: str | None = None) -> Optional[str]:
    """Compile share Desc to public HTML. None → keep trampoline work.html."""
    kind = str(share.get("kind") or "").strip().lower()
    if kind in {"plugin", "hardware", "os", "space", "machine", "boundary"}:
        return None
    code = str(share.get("code") or "").strip()
    if not code:
        return None
    try:
        from meta.description.serialize import from_json
        from meta.instantiation import TARGET_WEB_BUILD, instantiate, render_software_page

        desc = from_json(code)
        slug = str(share.get("slug") or "page")
        artifact = instantiate(desc, target=TARGET_WEB_BUILD, slug=slug)
        public_id = str(share["public_id"])
        artifact = replace(artifact, public_url=f"/w/{public_id}")
        pid = public_id

        def asset_href(asset_name: str) -> str:
            return f"/w/{pid}/assets/{asset_name}"

        html = render_software_page(
            artifact,
            step_action="",
            csrf_token="",
            page_key=page_key,
            asset_href=asset_href,
        )
    except (DescriptionError, InstantiationError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None
    badge = (
        '<aside id="zq-hosted-badge" style="position:fixed;right:12px;bottom:12px;'
        'z-index:9999;font:12px/1.4 system-ui,sans-serif">'
        '<a href="/download" style="background:#111;color:#fff;padding:6px 10px;'
        'text-decoration:none;border-radius:4px">Made with Zintriq</a></aside>'
    )
    if "</body>" in html:
        return html.replace("</body>", badge + "</body>", 1)
    return html + badge


def _normalize_share_asset(name: str, data: bytes) -> tuple[str, bytes]:
    from meta.instantiation import validate_asset_name

    blob = bytes(data or b"")
    if not blob or len(blob) > _ASSET_MAX:
        raise ValueError("image is missing or too large")
    sniffed = _sniff_image(blob)
    try:
        clean = validate_asset_name(name)
    except InstantiationError:
        clean = validate_asset_name(f"image.{sniffed}")
    ext = clean.rsplit(".", 1)[-1].lower()
    if ext == "jpeg":
        ext = "jpg"
    if sniffed != ext:
        raise ValueError("image type must match the file name")
    return clean, blob


def _sniff_image(data: bytes) -> str:
    raw = bytes(data or b"")
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    raise ValueError("not a local image")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _normalize_kind(value: Any) -> str:
    raw = str(value or "").strip()
    return _KIND_MAP.get(raw, raw or "system")[:40]


def _field_value(data: Any, key: str) -> Any:
    if not isinstance(data, dict):
        return None
    direct = data.get(key)
    if isinstance(direct, str) and direct.strip():
        return direct
    fields = data.get("fields")
    if isinstance(fields, dict):
        item = fields.get(key)
        if isinstance(item, dict):
            if "value" in item:
                return item.get("value")
            nested = _field_value(item, key)
            if nested is not None:
                return nested
        elif isinstance(item, str) and item.strip():
            return item
    return None


def _kind_from_code(raw: str) -> str:
    mapped = _KIND_MAP.get(str(raw or "").strip())
    if mapped:
        return mapped
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "system"
    if not isinstance(data, dict):
        return "system"
    if data.get("stamp") or str(data.get("file") or "").endswith(".zintriq-plugin.json"):
        return "plugin"
    return _normalize_kind(_field_value(data, "kind") or data.get("kind"))


def _title_from_code(raw: str, fallback: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    title = _field_value(data, "title") if isinstance(data, dict) else None
    if isinstance(title, str) and title.strip():
        return title.strip()[:_TITLE_MAX]
    return str(fallback or "Untitled")[:_TITLE_MAX]


def _load_share(public_id: str, *, require_hosting: bool = True) -> Optional[dict[str, Any]]:
    key = str(public_id or "").strip().lower()
    if not _SHARE_RE.match(key):
        return None
    from app import db

    with db() as conn:
        ensure_schema(conn)
        row = conn.execute(
            """
            SELECT s.*, u.email
            FROM desktop_shares s
            JOIN users u ON u.id = s.user_id
            WHERE s.public_id = ? AND s.listed = 1
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        share = dict(row)
        if require_hosting and not _owner_hosting_active(conn, int(share["user_id"])):
            return None
    return share


def _owner_hosting_active(conn, user_id: int) -> bool:
    from billing_platform import ensure_schema as billing_schema, subscription_hosting_active

    billing_schema(conn)
    return subscription_hosting_active(conn, int(user_id))
