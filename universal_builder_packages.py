"""Shared package protocol for official and community Builder packages."""

from __future__ import annotations

from universal_builder_capabilities import validate_capabilities


PACKAGE_TYPES = {
    "template", "starter_kit", "project", "page", "section", "component",
    "component_library", "capability", "theme", "workflow", "data_model",
    "integration", "plugin", "editor_extension", "runtime_adapter", "app_module",
}
ALLOWED_PERMISSION_PREFIXES = ("builder.", "workspace.", "booking.", "contact.", "customer.", "qr.", "store.")


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
    return errors


def package_summary(manifest: dict) -> dict:
    return {
        key: manifest.get(key)
        for key in (
            "id", "name", "description", "publisher", "version", "schema_version",
            "package_type", "dependencies", "required_capabilities", "permissions",
            "compatibility", "assets", "components", "workflows", "runtime_adapters", "migrations",
            "component_definitions", "design_system", "project_variables", "entry_resources",
            "design_token_dependencies", "lineage", "usage_rights", "release_notes",
        )
    }
