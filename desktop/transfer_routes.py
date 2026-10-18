"""Composition package HTTP is closed. Site zip lives at /api/builder-core/meta/sites."""

from __future__ import annotations

from flask import abort, send_from_directory

from desktop.server_mode import desktop_enabled
from desktop.transfer import asset_content_type


def register_transfer_routes(app, context, owned_project) -> None:
    del context, owned_project

    @app.post("/api/builder-core/transfer/export/<int:project_id>")
    def transfer_export(project_id: int):
        del project_id
        abort(404)

    @app.post("/api/builder-core/transfer/preview")
    def transfer_preview():
        abort(404)

    @app.post("/api/builder-core/transfer/commit")
    def transfer_commit():
        abort(404)

    @app.get("/uploads/<name>")
    def transfer_upload(name: str):
        if not desktop_enabled():
            abort(404)
        if asset_content_type(name) is None or "/" in name or "\\" in name:
            abort(404)
        from app import UPLOAD_DIR

        path = UPLOAD_DIR / name
        if not path.is_file() or path.is_symlink():
            abort(404)
        response = send_from_directory(UPLOAD_DIR, name, mimetype=asset_content_type(name))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        response.headers["Cache-Control"] = "private, max-age=3600"
        return response
