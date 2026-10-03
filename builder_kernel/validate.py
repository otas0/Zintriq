"""Single write-time validator for collection schemas and records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re

_FIELD_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_REMOTE_URL = re.compile(r"https?://", re.I)

ALLOWED_ROOT_KEYS = frozenset({"type", "properties", "required", "additionalProperties", "x-access"})
ALLOWED_PROPERTY_KEYS = frozenset({"type", "maxLength", "minimum", "maximum", "enum"})
ALLOWED_TYPES = frozenset({"string", "number", "integer", "boolean"})
ALLOWED_ACCESS_KEYS = frozenset({"public_read", "public_create"})
FORBIDDEN_KEYS = frozenset({"$ref", "$id", "$schema", "$defs", "definitions", "items", "allOf", "anyOf", "oneOf", "not"})
DEFAULT_MAX_LENGTH = 2000
MAX_NESTING = 2

MESSAGES = {
    "validation_error": "Some fields are invalid.",
    "adapter_unsupported": "This collection cannot be written.",
}


@dataclass
class FieldIssue:
    path: str
    code: str


@dataclass
class ValidationResult:
    ok: bool
    code: str = "validation_error"
    fields: list[FieldIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        if self.ok:
            return {"ok": True}
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": MESSAGES.get(self.code, MESSAGES["validation_error"]),
                "fields": [{"path": item.path, "code": item.code} for item in self.fields],
            },
        }

    def http_status(self) -> int:
        if self.ok:
            return 200
        if self.code == "adapter_unsupported":
            return 409
        return 400


def validate_schema(schema: Any, *, path: str = "") -> ValidationResult:
    issues: list[FieldIssue] = []
    _check_schema_node(schema, path or "", 0, issues, root=True)
    return ValidationResult(ok=not issues, fields=issues)


def validate_record(model_schema: Any, payload: Any) -> ValidationResult:
    schema_result = validate_schema(model_schema)
    if not schema_result.ok:
        return schema_result
    if not isinstance(payload, dict):
        return ValidationResult(ok=False, fields=[FieldIssue("data", "type")])
    schema = model_schema if isinstance(model_schema, dict) else {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    additional = schema.get("additionalProperties", True)
    issues: list[FieldIssue] = []
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    for name in required:
        if not isinstance(name, str):
            continue
        if name not in payload or payload[name] is None:
            issues.append(FieldIssue(name, "required"))
    for name, value in payload.items():
        if not isinstance(name, str) or _FIELD_NAME.match(name) is None:
            issues.append(FieldIssue(str(name)[:80], "invalid_name"))
            continue
        spec = properties.get(name)
        if spec is None:
            if additional is False:
                issues.append(FieldIssue(name, "additionalProperties"))
            continue
        issues.extend(_check_value(name, spec, value))
    return ValidationResult(ok=not issues, fields=issues)


def prepare_record_write(adapter: Any, model_schema: Any, payload: Any) -> ValidationResult:
    if str(adapter or "native") != "native":
        return ValidationResult(ok=False, code="adapter_unsupported")
    return validate_record(model_schema, payload)


def _check_schema_node(node: Any, path: str, depth: int, issues: list[FieldIssue], *, root: bool) -> None:
    if root and node is None:
        node = {}
    if depth > MAX_NESTING:
        issues.append(FieldIssue(path or "schema", "too_deep"))
        return
    if node is None:
        if root:
            return
        issues.append(FieldIssue(path or "schema", "type"))
        return
    if not isinstance(node, dict):
        issues.append(FieldIssue(path or "schema", "type"))
        return
    for key in node:
        if key in FORBIDDEN_KEYS or str(key).startswith("$"):
            issues.append(FieldIssue(_join(path, str(key)), "unsupported"))
        elif isinstance(node[key], str) and _REMOTE_URL.search(node[key]):
            issues.append(FieldIssue(_join(path, str(key)), "unsupported"))
    allowed = ALLOWED_ROOT_KEYS if root else ALLOWED_PROPERTY_KEYS
    for key in node:
        if key in FORBIDDEN_KEYS or str(key).startswith("$"):
            continue
        if key not in allowed:
            issues.append(FieldIssue(_join(path, str(key)), "unsupported"))
    type_name = node.get("type", "object" if root else None)
    if root:
        if type_name not in (None, "object"):
            issues.append(FieldIssue(_join(path, "type"), "type"))
        properties = node.get("properties", {})
        if properties is None:
            properties = {}
        if not isinstance(properties, dict):
            issues.append(FieldIssue(_join(path, "properties"), "type"))
            properties = {}
        for name, spec in properties.items():
            field_path = _join(path, "properties", str(name))
            if not isinstance(name, str) or _FIELD_NAME.match(name) is None:
                issues.append(FieldIssue(field_path, "invalid_name"))
                continue
            _check_schema_node(spec, field_path, depth + 1, issues, root=False)
        required = node.get("required", [])
        if required is None:
            required = []
        if required and not isinstance(required, list):
            issues.append(FieldIssue(_join(path, "required"), "type"))
        elif isinstance(required, list):
            for index, name in enumerate(required):
                if not isinstance(name, str) or name not in properties:
                    issues.append(FieldIssue(_join(path, "required", str(index)), "invalid_name"))
        additional = node.get("additionalProperties", True)
        if "additionalProperties" in node and not isinstance(additional, bool):
            issues.append(FieldIssue(_join(path, "additionalProperties"), "type"))
        _check_access(node.get("x-access"), path, additional is False, issues)
        return
    prop_type = node.get("type")
    if prop_type not in ALLOWED_TYPES:
        issues.append(FieldIssue(_join(path, "type") if "type" in node else path, "type"))
        return
    if "maxLength" in node:
        if prop_type != "string" or not _is_int(node["maxLength"]) or int(node["maxLength"]) < 0:
            issues.append(FieldIssue(_join(path, "maxLength"), "type"))
    if "minimum" in node and not _is_number(node["minimum"]):
        issues.append(FieldIssue(_join(path, "minimum"), "type"))
    if "maximum" in node and not _is_number(node["maximum"]):
        issues.append(FieldIssue(_join(path, "maximum"), "type"))
    if "enum" in node:
        if not isinstance(node["enum"], list) or not node["enum"]:
            issues.append(FieldIssue(_join(path, "enum"), "type"))


def _check_access(access: Any, path: str, additional_closed: bool, issues: list[FieldIssue]) -> None:
    if access is None:
        return
    access_path = _join(path, "x-access")
    if not isinstance(access, dict):
        issues.append(FieldIssue(access_path, "type"))
        return
    for key, value in access.items():
        item_path = _join(access_path, str(key))
        if key not in ALLOWED_ACCESS_KEYS:
            issues.append(FieldIssue(item_path, "unsupported"))
            continue
        if type(value) is not bool:
            issues.append(FieldIssue(item_path, "type"))
    public_create = access.get("public_create")
    if public_create is True and not additional_closed:
        issues.append(FieldIssue(_join(path, "additionalProperties"), "required"))


def _check_value(name: str, spec: Any, value: Any) -> list[FieldIssue]:
    if not isinstance(spec, dict):
        return [FieldIssue(name, "type")]
    expected = spec.get("type")
    issues: list[FieldIssue] = []
    if expected == "string":
        if type(value) is not str:
            return [FieldIssue(name, "type")]
        limit = spec["maxLength"] if _is_int(spec.get("maxLength")) else DEFAULT_MAX_LENGTH
        if len(value) > int(limit):
            issues.append(FieldIssue(name, "maxLength"))
    elif expected == "integer":
        if type(value) is not int:
            return [FieldIssue(name, "type")]
        issues.extend(_range_issues(name, spec, value))
    elif expected == "number":
        if type(value) not in (int, float):
            return [FieldIssue(name, "type")]
        issues.extend(_range_issues(name, spec, value))
    elif expected == "boolean":
        if type(value) is not bool:
            return [FieldIssue(name, "type")]
    else:
        return [FieldIssue(name, "type")]
    if "enum" in spec and isinstance(spec["enum"], list) and value not in spec["enum"]:
        issues.append(FieldIssue(name, "enum"))
    return issues


def _range_issues(name: str, spec: dict, value) -> list[FieldIssue]:
    issues = []
    if "minimum" in spec and _is_number(spec["minimum"]) and value < spec["minimum"]:
        issues.append(FieldIssue(name, "minimum"))
    if "maximum" in spec and _is_number(spec["maximum"]) and value > spec["maximum"]:
        issues.append(FieldIssue(name, "maximum"))
    return issues


def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_number(value: Any) -> bool:
    return type(value) in (int, float)


def _join(*parts: str) -> str:
    return ".".join(part for part in parts if part)
