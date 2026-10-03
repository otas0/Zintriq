"""S2 tracker path through public invoke. Detail/list/rate-limit stay xfail until K4."""

from __future__ import annotations

import json
import os
import re
import unittest
import uuid

os.environ.setdefault("SECRET_KEY", "test-builder-s2")

from builder_kernel.validate import validate_record, validate_schema


TRACKER = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
    "x-access": {"public_create": True, "public_read": True},
}


class TrackerScenarioTests(unittest.TestCase):
    def test_s2_blank_project_form_writes_validated_record(self):
        schema = TRACKER
        self.assertTrue(validate_schema(schema).ok)
        missing = validate_record(schema, {})
        self.assertFalse(missing.ok)
        self.assertEqual(missing.to_dict()["error"]["code"], "validation_error")
        self.assertTrue(any(item["code"] == "required" for item in missing.to_dict()["error"]["fields"]))
        self.assertTrue(validate_record(schema, {"title": "first entry"}).ok)

    @classmethod
    def setUpClass(cls):
        import app as app_module

        cls.app_module = app_module
        cls.app = app_module.app
        cls.app.config["TESTING"] = True
        with cls.app.app_context():
            app_module.init_db()

    def test_s2_published_form_invokes_create_record(self):
        os.environ.pop("ZINTRIQ_DESKTOP", None)
        from builder_http_support import auth_headers, login_editor

        client = self.app.test_client()
        _user_id, _ws, csrf = login_editor(client, self.app_module)
        headers = auth_headers(csrf)
        created = client.post(
            "/api/builder-core/projects",
            headers=headers,
            data=json.dumps({"name": f"S2 tracker {uuid.uuid4().hex[:8]}", "csrf_token": csrf}),
        )
        self.assertIn(created.status_code, (200, 201), created.get_data(as_text=True)[:500])
        project = created.get_json()
        project_id = project["id"]
        slug = project["slug"]
        model = client.post(
            f"/api/builder-core/projects/{project_id}/data-models",
            headers=headers,
            data=json.dumps({"csrf_token": csrf, "name": "notes", "schema": TRACKER}),
        )
        self.assertEqual(model.status_code, 201, model.get_data(as_text=True)[:400])
        model_key = model.get_json()["key"]
        boot = client.get(f"/api/builder-core/projects/{project_id}/bootstrap")
        self.assertEqual(boot.status_code, 200, boot.get_data(as_text=True)[:400])
        payload = boot.get_json()
        document = payload["active_document"]
        section = next(node for node in payload["nodes"] if node["component_type"] == "section")
        form = client.post(
            f"/api/builder-core/projects/{project_id}/nodes",
            headers=headers,
            data=json.dumps({
                "csrf_token": csrf,
                "document_id": document["id"],
                "component_type": "form",
                "parent_key": section["key"],
                "props": {"target_model": model_key, "title": "Notes"},
            }),
        )
        self.assertEqual(form.status_code, 201, form.get_data(as_text=True)[:400])
        form_key = form.get_json()["key"]
        field = client.post(
            f"/api/builder-core/projects/{project_id}/nodes",
            headers=headers,
            data=json.dumps({
                "csrf_token": csrf,
                "document_id": document["id"],
                "component_type": "form_field",
                "parent_key": form_key,
                "props": {"field_name": "title", "label": "Title", "required": True},
            }),
        )
        self.assertEqual(field.status_code, 201, field.get_data(as_text=True)[:400])
        action = client.post(
            f"/api/builder-core/projects/{project_id}/actions",
            headers=headers,
            data=json.dumps({
                "csrf_token": csrf,
                "document_id": document["id"],
                "node_key": form_key,
                "event_type": "on_submit",
                "action_type": "create_record",
                "configuration": {"model_key": model_key},
            }),
        )
        self.assertEqual(action.status_code, 201, action.get_data(as_text=True)[:400])
        self.assertEqual(action.get_json()["action_type"], "core/create_record")
        action_key = action.get_json()["key"]
        button = client.post(
            f"/api/builder-core/projects/{project_id}/nodes",
            headers=headers,
            data=json.dumps({
                "csrf_token": csrf,
                "document_id": document["id"],
                "component_type": "button",
                "parent_key": section["key"],
                "props": {"label": "Delete"},
            }),
        )
        self.assertEqual(button.status_code, 201, button.get_data(as_text=True)[:400])
        delete_action = client.post(
            f"/api/builder-core/projects/{project_id}/actions",
            headers=headers,
            data=json.dumps({
                "csrf_token": csrf,
                "document_id": document["id"],
                "node_key": button.get_json()["key"],
                "event_type": "on_click",
                "action_type": "delete_record",
                "configuration": {"model_key": model_key},
            }),
        )
        self.assertEqual(delete_action.status_code, 201, delete_action.get_data(as_text=True)[:400])
        unknown = client.post(
            f"/api/builder-core/projects/{project_id}/actions",
            headers=headers,
            data=json.dumps({
                "csrf_token": csrf,
                "document_id": document["id"],
                "node_key": form_key,
                "action_type": "not_a_real_action",
            }),
        )
        self.assertEqual(unknown.status_code, 400)
        published = client.post(
            f"/api/builder-core/projects/{project_id}/publish",
            headers=headers,
            data=json.dumps({"csrf_token": csrf, "note": "s2"}),
        )
        self.assertEqual(published.status_code, 201, published.get_data(as_text=True)[:400])

        with client.session_transaction() as sess:
            sess.pop("user_id", None)
            sess.pop("active_workspace_id", None)
        page = client.get(f"/build/{slug}/{document['key']}")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        csp = page.headers.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertNotRegex(csp, r"script-src[^;]*unsafe-inline")
        self.assertIn("/static/builder/published-runtime.js", html)
        self.assertNotIn("form-submit", html)
        self.assertNotRegex(html, r"<script(?![^>]*src=)")
        self.assertIn(f"data-action-key='{action_key}'", html)
        with client.session_transaction() as sess:
            public_csrf = sess["csrf_token"]

        invoke = f"/build/{slug}/{document['key']}/runtime/invoke"
        missing = client.post(
            invoke,
            headers=auth_headers(public_csrf),
            data=json.dumps({
                "csrf_token": public_csrf,
                "node_key": form_key,
                "action_key": action_key,
                "data": {},
            }),
        )
        self.assertEqual(missing.status_code, 400, missing.get_data(as_text=True)[:400])
        self.assertEqual(missing.get_json()["error"]["code"], "validation_error")
        with self.app_module.db() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) AS c FROM builder_data_records WHERE project_id=?",
                (project_id,),
            ).fetchone()["c"]
        self.assertEqual(rows, 0)

        ok = client.post(
            invoke,
            headers=auth_headers(public_csrf),
            data=json.dumps({
                "csrf_token": public_csrf,
                "node_key": form_key,
                "action_key": action_key,
                "data": {"title": "first entry"},
            }),
        )
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True)[:400])
        record_key = ok.get_json()["record_key"]
        self.assertTrue(str(record_key).startswith("rec_"))

        denied = client.post(
            invoke,
            headers=auth_headers(public_csrf),
            data=json.dumps({
                "csrf_token": public_csrf,
                "node_key": button.get_json()["key"],
                "action_key": delete_action.get_json()["key"],
                "record_key": record_key,
            }),
        )
        self.assertEqual(denied.status_code, 403)
        no_csrf = client.post(
            invoke,
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "node_key": form_key,
                "action_key": action_key,
                "data": {"title": "no csrf"},
            }),
        )
        self.assertEqual(no_csrf.status_code, 400)
        huge = client.post(
            invoke,
            headers=auth_headers(public_csrf),
            data=json.dumps({
                "csrf_token": public_csrf,
                "node_key": form_key,
                "action_key": action_key,
                "data": {"title": "x" * 40000},
            }),
        )
        self.assertEqual(huge.status_code, 413)
        missing_project = client.post(
            "/build/does-not-exist/home/runtime/invoke",
            headers=auth_headers(public_csrf),
            data=json.dumps({
                "csrf_token": public_csrf,
                "node_key": form_key,
                "action_key": action_key,
                "data": {"title": "x"},
            }),
        )
        missing_action = client.post(
            invoke,
            headers=auth_headers(public_csrf),
            data=json.dumps({
                "csrf_token": public_csrf,
                "node_key": form_key,
                "action_key": "no-such-action",
                "data": {"title": "x"},
            }),
        )
        self.assertEqual(missing_project.status_code, 404)
        self.assertEqual(missing_action.status_code, 404)
        self.assertEqual(missing_project.get_json()["error"]["code"], missing_action.get_json()["error"]["code"])
        gone = client.post(
            f"/build/{slug}/{document['key']}/form-submit",
            data={"csrf_token": public_csrf, "title": "legacy"},
        )
        self.assertEqual(gone.status_code, 404)
        with self.app_module.db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM builder_data_records WHERE project_id=? AND status!='archived'",
                (project_id,),
            ).fetchone()["c"]
        self.assertEqual(count, 1)

    def test_s2_blank_project_seed_currently_injects_official_product_card(self):
        os.environ.pop("ZINTRIQ_DESKTOP", None)
        from builder_http_support import auth_headers, login_editor

        client = self.app.test_client()
        _user_id, _ws, csrf = login_editor(client, self.app_module)
        created = client.post(
            "/api/builder-core/projects",
            headers=auth_headers(csrf),
            data=json.dumps({"name": f"Blank seed lock {uuid.uuid4().hex[:8]}", "csrf_token": csrf}),
        )
        self.assertIn(created.status_code, (200, 201), created.get_data(as_text=True)[:400])
        project_id = created.get_json()["id"]
        boot = client.get(f"/api/builder-core/projects/{project_id}/bootstrap")
        payload = boot.get_json()
        definitions = payload.get("component_definitions") or payload.get("definitions") or []
        keys = {item.get("component_key") or item.get("key") for item in definitions}
        self.assertIn(
            "official.product-card",
            keys,
            "seed_official_creator_system currently injects commerce UI; lock until K5",
        )
        bindings = payload.get("bindings") or []
        commerce = [item for item in bindings if "commerce.products" in json.dumps(item)]
        self.assertEqual(
            commerce,
            [],
            "blank projects currently have no customer-site, so commerce.products is not bound",
        )

    @unittest.expectedFailure
    def test_s2_public_detail_and_live_list(self):
        self.fail("needs K4 /build/<slug>/records/<model>/<record> and live repeater")

    @unittest.expectedFailure
    def test_s2_rate_limit_and_honeypot(self):
        self.fail("needs K4 rate limit and honeypot")


class PersonalToolScenarioTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_s4_personal_workspace_has_no_store(self):
        self.fail("needs K5 workspaces.type=personal without ensure_workspace_store")

    @unittest.expectedFailure
    def test_s4_publish_is_build_url_not_hybrid_home(self):
        self.fail("needs K5 publish assertions for blank personal projects")


if __name__ == "__main__":
    unittest.main()
