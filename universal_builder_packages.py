"""Shared package protocol for official and community Builder packages."""

from __future__ import annotations

from copy import deepcopy

from universal_builder_capabilities import validate_capabilities


PACKAGE_TYPES = {
    "template", "starter_kit", "project", "page", "section", "component",
    "component_library", "capability", "theme", "workflow", "data_model",
    "integration", "plugin", "editor_extension", "runtime_adapter", "app_module",
}
ALLOWED_PERMISSION_PREFIXES = ("builder.", "workspace.", "booking.", "contact.", "customer.", "qr.", "store.")
# K6: minimal capability-contract contribution points. No workflow merge.
CONTRIBUTES_KEYS = ("editor", "sidebar", "commands")


def validate_contributes(contributes) -> list[str]:
    """Validate package contributes. Missing contributes is allowed."""
    if contributes is None:
        return []
    if not isinstance(contributes, dict):
        return ["contributes must be an object"]
    errors: list[str] = []
    for key in contributes:
        if key not in CONTRIBUTES_KEYS:
            errors.append(f"Unsupported contributes key: {key}")
    for key in CONTRIBUTES_KEYS:
        if key not in contributes:
            continue
        items = contributes[key]
        if not isinstance(items, list):
            errors.append(f"contributes.{key} must be a list")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"contributes.{key}[{index}] must be an object")
                continue
            item_id = item.get("id")
            title = item.get("title")
            if not isinstance(item_id, str) or not item_id.strip():
                errors.append(f"contributes.{key}[{index}].id is required")
            if not isinstance(title, str) or not title.strip():
                errors.append(f"contributes.{key}[{index}].title is required")
    return errors


def normalize_contributes(contributes) -> dict:
    """Return a stable contributes object with only allowed keys."""
    source = contributes if isinstance(contributes, dict) else {}
    result = {key: [] for key in CONTRIBUTES_KEYS}
    for key in CONTRIBUTES_KEYS:
        items = source.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not item_id or not title:
                continue
            result[key].append({"id": item_id, "title": title})
    return result


def validate_package_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []
    required = ("id", "name", "publisher", "version", "schema_version", "package_type")
    for key in required:
        if manifest.get(key) in (None, "", []):
            errors.append(f"Missing {key}")
    if manifest.get("package_type") not in PACKAGE_TYPES:
        errors.append("Unsupported package_type")
    capabilities = manifest.get("required_capabilities") or []
    if not isinstance(capabilities, list):
        errors.append("required_capabilities must be a list")
    else:
        errors.extend(validate_capabilities(capabilities))
    permissions = manifest.get("permissions") or []
    if not isinstance(permissions, list):
        errors.append("permissions must be a list")
    else:
        for permission in permissions:
            if not isinstance(permission, str) or not permission.startswith(ALLOWED_PERMISSION_PREFIXES):
                errors.append(f"Unsupported package permission: {permission}")
    compatibility = manifest.get("compatibility") or {}
    if not isinstance(compatibility, dict) or not compatibility.get("builder_schema"):
        errors.append("compatibility.builder_schema is required")
    if "contributes" in manifest:
        errors.extend(validate_contributes(manifest.get("contributes")))
    return errors


def package_summary(manifest: dict) -> dict:
    summary = {
        key: manifest.get(key)
        for key in (
            "id", "name", "description", "publisher", "version", "schema_version",
            "package_type", "dependencies", "required_capabilities", "permissions",
            "compatibility", "assets", "components", "workflows", "runtime_adapters", "migrations",
            "component_definitions", "design_system", "project_variables", "entry_resources",
            "design_token_dependencies", "lineage", "usage_rights", "release_notes",
        )
    }
    if "contributes" in manifest:
        summary["contributes"] = deepcopy(normalize_contributes(manifest.get("contributes")))
    return summary
