"""MVP Responses API — unified customer submission endpoints."""

from __future__ import annotations

from flask import abort, jsonify, request, session

from bos.responses import get_workspace_response, list_workspace_responses, response_to_api


def register_mvp_responses_platform(app) -> None:
    from app import current_user, db, login_required
    from bos.permissions import has_permission

    def uid() -> int:
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    def ws_id() -> int | None:
        return session.get("active_workspace_id")

    def _guard(conn, permission: str) -> None:
        ws = ws_id()
        if ws and not has_permission(conn, uid(), int(ws), permission):
            abort(403)

    @app.get("/api/responses")
    @login_required
    def api_responses_list():
        ws = ws_id()
        if not ws:
            return jsonify([])
        q = request.args.get("q", "").strip()
        response_type = request.args.get("type", "").strip() or None
        experience_id = request.args.get("experience_id", type=int)
        with db() as conn:
            _guard(conn, "feedback.read")
            rows = list_workspace_responses(
                conn, int(ws), response_type=response_type, experience_id=experience_id, q=q or None,
            )
            return jsonify([response_to_api(r, conn) for r in rows])

    @app.get("/api/responses/<int:response_id>")
    @login_required
    def api_responses_detail(response_id: int):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "feedback.read")
            row = get_workspace_response(conn, response_id, int(ws))
            if not row:
                abort(404)
            return jsonify(response_to_api(row, conn))
