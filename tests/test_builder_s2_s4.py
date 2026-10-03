"""S2 tracker and S4 personal-tool paths. Remaining cases turn green in K3–K6."""

from __future__ import annotations

import unittest

from builder_kernel.validate import validate_record, validate_schema


class TrackerScenarioTests(unittest.TestCase):
    def test_s2_blank_project_form_writes_validated_record(self):
        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
            "x-access": {"public_create": True, "public_read": True},
        }
        self.assertTrue(validate_schema(schema).ok)
        missing = validate_record(schema, {})
        self.assertFalse(missing.ok)
        self.assertEqual(missing.to_dict()["error"]["code"], "validation_error")
        self.assertTrue(any(item["code"] == "required" for item in missing.to_dict()["error"]["fields"]))
        self.assertTrue(validate_record(schema, {"title": "first entry"}).ok)

    @unittest.expectedFailure
    def test_s2_published_form_invokes_create_record(self):
        self.fail("needs K3 public invoke")

    @unittest.expectedFailure
    def test_s2_public_detail_and_live_list(self):
        self.fail("needs K4 /build/<slug>/records/<model>/<record> and live repeater")

    @unittest.expectedFailure
    def test_s2_anonymous_limits_and_csp(self):
        self.fail("needs K4 rate limit, body cap, and published CSP")


class PersonalToolScenarioTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_s4_personal_workspace_has_no_store(self):
        self.fail("needs K5 workspaces.type=personal without ensure_workspace_store")

    @unittest.expectedFailure
    def test_s4_publish_is_build_url_not_hybrid_home(self):
        self.fail("needs K5 publish assertions for blank personal projects")


if __name__ == "__main__":
    unittest.main()
