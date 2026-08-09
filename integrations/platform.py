"""Integration layer HTTP routes — status, profiles, subscriptions, webhooks."""

from __future__ import annotations

from flask import abort, jsonify, request


def register_integrations_core(app) -> None:
    from app import current_user, db, login_required
    from bos.permissions import has_permission
    from integrations import init_integrations_core_tables
    from integrations.auth.service import AuthService
    from integrations.config import integration_status
    from integrations.payment.service import PaymentService
    from integrations.subscription import subscription_to_api
    from integrations.user_profile import profile_to_api, sync_profile_from_user_row
    from integrations.webhooks import handle_payment_webhook

    app.init_integrations_core_tables = init_integrations_core_tables

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    @app.get("/api/integrations/status")
    @login_required
    def api_integrations_status():
        return jsonify(integration_status())

    @app.get("/api/me/profile")
    @login_required
    def api_me_profile():
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE id=?", (uid(),)).fetchone()
            if not user:
                abort(404)
            profile = AuthService.profile(conn, uid())
            if not profile:
                from integrations.config import auth_provider_name
                provider = "firebase" if user["firebase_uid"] else auth_provider_name()
                profile = sync_profile_from_user_row(conn, user, auth_provider=provider)
            memberships = [
                dict(r) for r in conn.execute(
                    """SELECT wm.workspace_id, wm.role, wm.status, w.name AS workspace_name
                       FROM workspace_members wm
                       JOIN workspaces w ON w.id=wm.workspace_id
                       WHERE wm.user_id=? AND wm.status='active'""",
                    (uid(),),
                ).fetchall()
            ]
        return jsonify({"profile": profile, "memberships": memberships})

    @app.get("/api/workspaces/<int:workspace_id>/subscription")
    @login_required
    def api_workspace_subscription(workspace_id):
        with db() as conn:
            if not has_permission(conn, uid(), workspace_id, "workspace.read"):
                abort(403)
            sub = PaymentService.subscription(conn, workspace_id)
        return jsonify(sub)

    @app.post("/api/integrations/webhooks/payment/<provider_slug>")
    def api_payment_webhook(provider_slug):
        """External payment webhooks — CSRF exempt."""
        payload = request.get_data()
        signature = request.headers.get("Stripe-Signature") or request.headers.get("X-Webhook-Signature")
        with db() as conn:
            result = handle_payment_webhook(conn, provider_slug.lower(), payload, signature)
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    app.integrations_auth_service = AuthService
    app.integrations_payment_service = PaymentService
