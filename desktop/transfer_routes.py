"""Desktop-only project export and import routes.

Web mode returns 404. Export uses the same workspace ownership check as the
Builder APIs and reads inside a read-only transaction.
"""

from __future__ import annotations

import os

from flask import abort, jsonify, request, send_from_directory

from desktop.server_mode import desktop_enabled
from desktop.transfer import TransferError, asset_content_type, export_project, import_project, preview_package


def register_transfer_routes(app, context, owned_project) -> None:
    @app.post("/api/builder-core/transfer/export/<int:project_id>")
    def transfer_export(project_id: int):
        if not desktop_enabled():
            abort(404)
        _user_id, workspace_id = context("builder.read")
        from app import DATABASE, UPLOAD_DIR, db
        from desktop.sqlite_io import open_connection

        with db() as conn:
            owned_project(conn, project_id, workspace_id)
        reader = open_connection(DATABASE)
        try:
            blob = export_project(
                reader,
                project_id,
                workspace_id,
                UPLOAD_DIR,
                app_version=os.environ.get("ZINTRIQ_APP_VERSION") or "0.0.0",
            )
        except TransferError as exc:
            status = 404 if exc.code == "not_found" else 400
            return jsonify({"error": exc.message}), status
        finally:
            reader.close()
        response = app.response_class(blob, mimetype="application/zip")
        response.headers["Content-Disposition"] = "attachment; filename=project.zintriq"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/api/builder-core/transfer/preview")
    def transfer_preview():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        try:
            preview = preview_package(
                request.get_data(cache=False),
                expected_sha256=request.headers.get("X-Zintriq-Package-Sha256"),
            )
        except TransferError as exc:
            return jsonify({"error": exc.message}), 400
        return jsonify(preview)

    @app.post("/api/builder-core/transfer/commit")
    def transfer_commit():
        if not desktop_enabled():
            abort(404)
        user_id, workspace_id = context("builder.update")
        from app import DATABASE, UPLOAD_DIR, db
        from desktop.sqlite_io import open_connection

        with db() as conn:
            conn.rollback()
        writer = open_connection(DATABASE)
        try:
            try:
                result = import_project(
                    writer,
                    request.get_data(cache=False),
                    upload_dir=UPLOAD_DIR,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    enable_keys=_enable_keys(request.headers.get("X-Zintriq-Enable") or ""),
                    expected_sha256=request.headers.get("X-Zintriq-Package-Sha256"),
                )
            except TransferError as exc:
                return jsonify({"error": exc.message}), 400
        finally:
            writer.close()
        return jsonify(result)

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


def _enable_keys(header: str) -> set[str]:
    if not header.strip():
        return set()
    return {part.strip() for part in header.split(",") if part.strip()}
