"""Write-time schema and record validation."""

from __future__ import annotations

import unittest

from builder_kernel.registry import kernel
from builder_kernel.validate import prepare_record_write, validate_record, validate_schema


TRACKER_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string", "maxLength": 80}},
    "required": ["title"],
    "additionalProperties": False,
    "x-access": {"public_create": True, "public_read": True},
}


class SchemaSubsetTests(unittest.TestCase):
    def test_accepts_tracker_schema_and_record(self):
        self.assertTrue(validate_schema(TRACKER_SCHEMA).ok)
        self.assertTrue(validate_record(TRACKER_SCHEMA, {"title": "Walk"}).ok)

    def test_empty_object_schema_is_valid(self):
        self.assertTrue(validate_schema({}).ok)
        self.assertTrue(validate_schema(None).ok)

    def test_rejects_ref_url_and_nested_object(self):
        self.assertFalse(validate_schema({"$ref": "#/defs/x"}).ok)
        self.assertFalse(validate_schema({"type": "object", "properties": {"u": {"type": "string", "format": "https://example.com"}}}).ok)
        nested = {"type": "object", "properties": {"child": {"type": "object", "properties": {"n": {"type": "string"}}}}}
        self.assertFalse(validate_schema(nested).ok)

    def test_rejects_unknown_property_types_and_names(self):
        self.assertFalse(validate_schema({"type": "object", "properties": {"items": {"type": "array"}}}).ok)
        self.assertFalse(validate_schema({"type": "object", "properties": {"bad-name": {"type": "string"}}}).ok)

    def test_public_create_requires_closed_additional_properties(self):
        open_schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "x-access": {"public_create": True},
        }
        result = validate_schema(open_schema)
        self.assertFalse(result.ok)
        self.assertEqual(result.to_dict()["error"]["code"], "validation_error")
        self.assertTrue(any(item["path"] == "additionalProperties" for item in result.to_dict()["error"]["fields"]))

    def test_x_access_only_allows_two_booleans(self):
        schema = {
            "type": "object",
            "properties": {},
            "x-access": {"public_read": True, "public_update": False},
        }
        result = validate_schema(schema)
        self.assertFalse(result.ok)
        self.assertTrue(any(item["code"] == "unsupported" for item in result.to_dict()["error"]["fields"]))

    def test_record_errors_use_fixed_envelope(self):
        result = validate_record(TRACKER_SCHEMA, {"title": 1, "extra": True})
        body = result.to_dict()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "validation_error")
        self.assertEqual(body["error"]["message"], "Some fields are invalid.")
        codes = {item["path"]: item["code"] for item in body["error"]["fields"]}
        self.assertEqual(codes["title"], "type")
        self.assertEqual(codes["extra"], "additionalProperties")
        self.assertNotIn("traceback", str(body).lower())
        self.assertNotIn("sqlite", str(body).lower())

    def test_string_default_max_length_and_enum(self):
        schema = {"type": "object", "properties": {"title": {"type": "string"}, "color": {"type": "string", "enum": ["red"]}}}
        too_long = validate_record(schema, {"title": "x" * 2001})
        self.assertFalse(too_long.ok)
        self.assertEqual(too_long.fields[0].code, "maxLength")
        self.assertFalse(validate_record(schema, {"color": "blue"}).ok)

    def test_adapter_unsupported_does_not_look_like_validation(self):
        result = prepare_record_write("legacy", TRACKER_SCHEMA, {"title": "Walk"})
        self.assertFalse(result.ok)
        self.assertEqual(result.http_status(), 409)
        self.assertEqual(result.to_dict()["error"]["code"], "adapter_unsupported")
        self.assertEqual(result.to_dict()["error"]["fields"], [])

    def test_create_record_action_uses_the_same_validator(self):
        kernel.ensure_core()
        handler = kernel.action("core/create_record")["handler"]
        result = handler({"adapter": "native", "schema": TRACKER_SCHEMA, "payload": {}})
        self.assertFalse(result.ok)
        self.assertEqual(result.to_dict()["error"]["code"], "validation_error")

    def test_dirty_payload_stays_readable_and_fails_rewrite(self):
        dirty = {"title": 3}
        self.assertFalse(validate_record(TRACKER_SCHEMA, dirty).ok)
        self.assertEqual(dirty, {"title": 3})
        rewrite = prepare_record_write("native", TRACKER_SCHEMA, dirty)
        self.assertEqual(rewrite.to_dict()["error"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
