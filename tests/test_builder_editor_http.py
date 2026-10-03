"""HTTP coverage that editor model/record writes go through kernel validators."""

from __future__ import annotations

import json
import os
import unittest
import uuid

os.environ.setdefault("SECRET_KEY", "test-builder-http")


TRACKER = {
    "type": "object",
    "properties": {"title": {"type": "string", "maxLength": 80}},
    "required": ["title"],
    "additionalProperties": False,
    "x-access": {"public_create": True, "public_read": True},
}


class EditorWriteHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        cls.app_module = app_module
        cls.app = app_module.app
        cls.app.config["TESTING"] = True
        with cls.app.app_context():
            app_module.init_db()

    def setUp(self):
        os.environ.pop("ZINTRIQ_DESKTOP", None)
        from builder_http_support import auth_headers, login_editor

        self.client = self.app.test_client()
        self.user_id, self.workspace_id, self.csrf = login_editor(self.client, self.app_module)
        self.headers = auth_headers(self.csrf)

    def _create_project(self):
        created = self.client.post(
            "/api/builder-core/projects",
            headers=self.headers,
            data=json.dumps({"name": f"HTTP validator {uuid.uuid4().hex[:8]}", "csrf_token": self.csrf}),
        )
        self.assertIn(created.status_code, (200, 201), created.get_data(as_text=True)[:400])
        payload = created.get_json()
        return payload["id"]

    def test_illegal_schema_and_x_access_rejected_on_model_post_and_patch(self):
        project_id = self._create_project()
        bad_ref = self.client.post(
            f"/api/builder-core/projects/{project_id}/data-models",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "name": "bad",
                "schema": {"$ref": "#/definitions/x"},
            }),
        )
        self.assertEqual(bad_ref.status_code, 400, bad_ref.get_data(as_text=True)[:400])
        self.assertFalse((bad_ref.get_json() or {}).get("ok", True))

        bad_access = self.client.post(
            f"/api/builder-core/projects/{project_id}/data-models",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "name": "access",
                "schema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "x-access": {"public_create": "yes", "public_write": True},
                },
            }),
        )
        self.assertEqual(bad_access.status_code, 400, bad_access.get_data(as_text=True)[:400])

        ok = self.client.post(
            f"/api/builder-core/projects/{project_id}/data-models",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "notes", "schema": TRACKER}),
        )
        self.assertEqual(ok.status_code, 201, ok.get_data(as_text=True)[:400])
        key = ok.get_json()["key"]
        patch = self.client.patch(
            f"/api/builder-core/projects/{project_id}/data-models/{key}",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "schema": {"$id": "https://evil.example/schema"}}),
        )
        self.assertEqual(patch.status_code, 400, patch.get_data(as_text=True)[:400])

    def test_record_post_and_patch_use_prepare_record_write(self):
        project_id = self._create_project()
        model = self.client.post(
            f"/api/builder-core/projects/{project_id}/data-models",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "notes", "schema": TRACKER}),
        )
        self.assertEqual(model.status_code, 201, model.get_data(as_text=True)[:400])
        key = model.get_json()["key"]
        missing = self.client.post(
            f"/api/builder-core/projects/{project_id}/data-models/{key}/records",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "data": {}}),
        )
        self.assertEqual(missing.status_code, 400)
        body = missing.get_json()
        self.assertEqual(body["error"]["code"], "validation_error")
        self.assertTrue(any(item["code"] == "required" for item in body["error"]["fields"]))
        with self.app_module.db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM builder_data_records WHERE project_id=?",
                (project_id,),
            ).fetchone()["c"]
        self.assertEqual(count, 0)

        created = self.client.post(
            f"/api/builder-core/projects/{project_id}/data-models/{key}/records",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "data": {"title": "ok"}}),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        record_key = created.get_json()["key"]
        bad_patch = self.client.patch(
            f"/api/builder-core/projects/{project_id}/data-models/{key}/records/{record_key}",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "data": {"title": 12}}),
        )
        self.assertEqual(bad_patch.status_code, 400)
        self.assertEqual(bad_patch.get_json()["error"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
