"""Universal Builder Component Registry.

This module provides the Universal Builder's view of the component system.

ARCHITECTURE
============

builder_components.py (canonical source)
    ↓
universal_component_registry.py (Universal Builder ownership boundary)
    ↓
universal_builder_core.py, universal_builder_migration.py

LEGACY ISOLATION
================

Legacy QR Builder imports directly from builder_components.py:
    - qr_experience_builder.py
    - qr_experience_platform.py

Universal Builder imports from this module:
    - universal_builder_core.py
    - universal_builder_migration.py

This creates an explicit ownership boundary. Changes to Universal-specific
metadata in this module do not affect Legacy. Changes to builder_components.py
affect both systems (as intended for the shared immutable contract).

SHARED IMMUTABLE CONTRACT
==========================

builder_components.py contains COMPONENT_REGISTRY and ACTION_REGISTRY which
are written once at import time via _upgrade_registry(), then remain immutable.
All consumers use deepcopy (via registry_payload()) or read-only lookups.

This module re-exports those registries and adds Universal-specific enrichment
without mutating the underlying data structures.
"""

from __future__ import annotations

from copy import deepcopy

from builder_components import (
    COMPONENT_REGISTRY,
    ACTION_REGISTRY,
    new_node_key,
    normalize_component,
    normalize_action,
    registry_payload,
    BLOCK_TYPES,
    ACTION_TYPES,
)


__all__ = [
    "COMPONENT_REGISTRY",
    "ACTION_REGISTRY",
    "UNIVERSAL_COMPONENT_REGISTRY",
    "new_node_key",
    "normalize_component",
    "normalize_action",
    "registry_payload",
    "universal_registry_payload",
    "BLOCK_TYPES",
    "ACTION_TYPES",
]


UNIVERSAL_COMPONENT_REGISTRY: dict[str, dict] = {}


def _enrich_universal_metadata() -> None:
    """Add Universal Builder-specific metadata to component definitions.

    This enrichment is Universal-only and does not mutate the shared
    COMPONENT_REGISTRY from builder_components.py.
    """
    category_display_names = {
        "layout": "Layout",
        "content": "Content",
        "interaction": "Interaction",
        "data": "Data & Forms",
        "media": "Media",
        "commerce": "Commerce",
        "business": "Business",
        "composite": "Composite",
        "application": "Application",
        "components": "User Components",
    }

    component_display_names = {
        "stack": "Stack",
        "grid": "Grid",
        "overlay": "Overlay",
        "section": "Section",
        "heading": "Heading",
        "button": "Button",
        "repeater": "Repeater",
        "form": "Form",
        "form_field": "Form Field",
        "header": "Header",
        "text": "Text",
        "image": "Image",
        "info": "Information",
        "actions": "Buttons",
        "shop": "Storefront",
        "survey": "Survey",
        "booking": "Booking",
        "check_in": "Check-in",
        "contact": "Contact",
        "navigation": "Navigation",
        "hero": "Hero",
        "store_grid": "Store Grid",
        "app_shell": "App Shell",
        "app_module": "App Module",
        "component_instance": "Component Instance",
    }

    for component_type, spec in COMPONENT_REGISTRY.items():
        enriched = deepcopy(spec)

        enriched["display_name"] = component_display_names.get(
            component_type, spec.get("label", component_type)
        )
        enriched["category_display"] = category_display_names.get(
            spec.get("category", ""), spec.get("category", "")
        )

        if "property_schema" in enriched:
            schema = enriched["property_schema"]
            if isinstance(schema, dict) and "properties" in schema:
                for prop_name, prop_def in schema["properties"].items():
                    if isinstance(prop_def, dict):
                        if "editor" not in prop_def:
                            prop_type = prop_def.get("type", "string")
                            if prop_type == "boolean":
                                prop_def["editor"] = "boolean"
                            elif prop_type == "number":
                                prop_def["editor"] = "number"
                            elif "enum" in prop_def:
                                prop_def["editor"] = "select"
                            else:
                                prop_def["editor"] = "text"

                        if prop_def.get("editor") == "select" and "enum" not in prop_def:
                            fields = spec.get("fields", {})
                            if prop_name in fields:
                                field_type = fields[prop_name]
                                if field_type == "select":
                                    defaults = spec.get("defaults", {})
                                    if prop_name in defaults:
                                        prop_def.setdefault(
                                            "enum", [defaults[prop_name]]
                                        )

        UNIVERSAL_COMPONENT_REGISTRY[component_type] = enriched


_enrich_universal_metadata()


def universal_registry_payload() -> dict:
    """Return the Universal Builder registry with enriched metadata.

    This is separate from registry_payload() to maintain the ownership
    boundary. Universal Builder should use this function.
    """
    return {
        "schema_version": 2,
        "components": deepcopy(UNIVERSAL_COMPONENT_REGISTRY),
        "actions": deepcopy(ACTION_REGISTRY),
    }
