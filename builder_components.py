"""Canonical Component Registry V2.

The legacy ``defaults`` and ``fields`` keys intentionally remain available to
the QR Experience editor.  Universal Builder consumes the richer contract in
the same registry, so components are defined once and adapted by each editor.
"""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4


COMPONENT_REGISTRY: dict[str, dict] = {
    "component_instance": {
        "label": "Component Instance", "category": "components", "kind": "user_component",
        "description": "A synchronized instance of a reusable project component.",
        "defaults": {"definition_id": 0, "variant": "default"},
        "fields": {"definition_id": "number", "variant": "select"},
        "slots": {"default": {"accepts": ["*"]}},
        "allowed_parents": ["root", "section", "stack", "grid", "app_shell", "repeater"],
        "editor": {"adapter": "component-instance"}, "runtime": {"adapter": "component-definition"},
    },
    "stack": {
        "label": "Stack", "category": "layout", "kind": "composite",
        "defaults": {"direction": "column", "gap": "16px", "align": "stretch", "distribution": "start", "wrap": False},
        "fields": {"direction": "select", "gap": "text", "align": "select", "distribution": "select", "wrap": "boolean"},
        "slots": {"default": {"accepts": ["*"]}},
    },
    "grid": {
        "label": "Grid", "category": "layout", "kind": "composite",
        "defaults": {"columns": 3, "gap": "16px", "min_column_width": "220px", "auto_fit": True},
        "fields": {"columns": "number", "gap": "text", "min_column_width": "text", "auto_fit": "boolean"},
        "slots": {"default": {"accepts": ["*"]}},
    },
    "overlay": {
        "label": "Overlay", "category": "layout", "kind": "composite",
        "defaults": {"min_height": "320px"}, "fields": {"min_height": "text"},
        "slots": {"default": {"accepts": ["*"]}},
    },
    "section": {
        "label": "Section", "category": "layout",
        "defaults": {"tag": "section"}, "fields": {"tag": "select"},
        "slots": {"default": {"accepts": ["*"]}},
    },
    "heading": {
        "label": "Heading", "category": "content",
        "defaults": {"text": "New heading", "level": 2},
        "fields": {"text": "text", "level": "select"},
    },
    "button": {
        "label": "Button", "category": "interaction",
        "defaults": {"label": "Continue", "variant": "primary"},
        "fields": {"label": "text", "variant": "select"},
        "events": ["click"],
    },
    "repeater": {
        "label": "Repeater", "category": "data",
        "defaults": {"empty_text": "No items yet"},
        "fields": {"empty_text": "text"},
        "slots": {"item": {"accepts": ["*"]}},
        "data_inputs": ["items"],
    },
    "form": {
        "label": "Form", "category": "data", "kind": "composite",
        "description": "Collect data and save it to a collection.",
        "defaults": {"title": "Submit", "submit_label": "Submit", "success_message": "Submitted successfully", "failure_message": "Something went wrong. Please try again.", "target_model": ""},
        "fields": {"title": "text", "submit_label": "text", "success_message": "text", "failure_message": "text", "target_model": "resource"},
        "slots": {"fields": {"accepts": ["form_field"]}},
        "events": ["submit"],
        "data_inputs": ["target_model"],
    },
    "form_field": {
        "label": "Form Field", "category": "data",
        "description": "A single input within a form.",
        "defaults": {"label": "Field", "field_name": "field", "field_type": "text", "placeholder": "", "required": False, "help_text": ""},
        "fields": {"label": "text", "field_name": "text", "field_type": "select", "placeholder": "text", "required": "boolean", "help_text": "text"},
        "property_schema": {"type": "object", "properties": {
            "label": {"type": "string"}, "field_name": {"type": "string"},
            "field_type": {"type": "string", "enum": ["text", "email", "number", "date", "textarea", "checkbox", "select"]},
            "placeholder": {"type": "string"}, "required": {"type": "boolean"}, "help_text": {"type": "string"},
        }},
        "allowed_parents": ["form"],
    },
    "header": {
        "label": "Header",
        "category": "content",
        "defaults": {"title": "", "subtitle": ""},
        "fields": {"title": "text", "subtitle": "text"},
        "allowed_parents": ["root", "section", "app_shell"],
    },
    "text": {
        "label": "Text",
        "category": "content",
        "defaults": {"body": ""},
        "fields": {"body": "textarea"},
    },
    "image": {
        "label": "Image",
        "category": "media",
        "defaults": {"src": "", "alt": ""},
        "fields": {"src": "image", "alt": "text"},
    },
    "info": {
        "label": "Information",
        "category": "content",
        "defaults": {"title": "", "body": ""},
        "fields": {"title": "text", "body": "textarea"},
    },
    "actions": {
        "label": "Buttons",
        "category": "interaction",
        "defaults": {"title": ""},
        "fields": {"title": "text"},
    },
    "shop": {
        "label": "Storefront",
        "category": "commerce",
        "defaults": {"label": "View shop", "subtitle": ""},
        "fields": {"label": "text", "subtitle": "text"},
    },
    "survey": {
        "label": "Survey",
        "category": "interaction",
        "defaults": {"title": "Your feedback", "body": ""},
        "fields": {"title": "text", "body": "textarea"},
    },
    "booking": {
        "label": "Booking",
        "category": "interaction",
        "defaults": {"title": "Book your visit"},
        "fields": {"title": "text"},
    },
    "check_in": {
        "label": "Check-in",
        "category": "interaction",
        "defaults": {"title": "Confirm your arrival"},
        "fields": {"title": "text"},
    },
    "contact": {
        "label": "Contact",
        "category": "business",
        "defaults": {"title": "Contact", "show_store": True},
        "fields": {"title": "text", "show_store": "boolean"},
    },
    "navigation": {
        "label": "Navigation", "category": "composite",
        "kind": "composite",
        "defaults": {"brand": "Zintriq", "links": "Home|/\nPlaces|/venues\nAccount|/account"},
        "fields": {"brand": "text", "links": "textarea"},
        "slots": {"actions": {"accepts": ["button"]}},
        "allowed_parents": ["root", "section", "app_shell"],
        "events": ["click"],
    },
    "hero": {
        "label": "Hero", "category": "composite", "kind": "composite",
        "defaults": {"eyebrow": "Build anything", "title": "Everything you need, in one place", "body": "Discover stores, services and experiences around you.", "image": ""},
        "fields": {"eyebrow": "text", "title": "text", "body": "textarea", "image": "image"},
        "slots": {"actions": {"accepts": ["button"]}, "content": {"accepts": ["text", "image"]}},
        "allowed_parents": ["root", "section"],
    },
    "store_grid": {
        "label": "Store Grid", "category": "commerce", "kind": "capability",
        "description": "Display live stores from the existing Commerce system.",
        "defaults": {"title": "Stores near you", "limit": 6, "columns": 3, "show_description": True, "empty_text": "No stores yet"},
        "fields": {"title": "text", "limit": "number", "columns": "number", "show_description": "boolean", "empty_text": "text"},
        "data_inputs": ["items"], "events": ["select"],
        "allowed_parents": ["root", "section"],
        "required_capabilities": ["commerce", "data"],
        "runtime": {"adapter": "domain-data", "data_source": "commerce.stores"},
    },
    "app_shell": {
        "label": "App Shell", "category": "application", "kind": "composite",
        "description": "Builder-controlled shell for operational applications.",
        "defaults": {"brand": "Zintriq", "logo": "", "density": "comfortable", "accent": "#f3cf32"},
        "fields": {"brand": "text", "logo": "image", "density": "select", "accent": "color"},
        "slots": {"sidebar": {"accepts": ["navigation"]}, "header": {"accepts": ["header", "text", "button"]}, "content": {"accepts": ["app_module", "section"]}},
        "allowed_parents": ["root"],
        "required_capabilities": ["auth"],
        "supported_surfaces": ["business"],
    },
    "app_module": {
        "label": "App Module", "category": "application", "kind": "app_module",
        "description": "Mount a registered mature application module.",
        "defaults": {"module_id": "commerce.store_manager", "title": "Store Manager", "height": 720},
        "fields": {"module_id": "select", "title": "text", "height": "number"},
        "events": ["ready", "change"],
        "allowed_parents": ["app_shell", "section"],
        "required_capabilities": ["auth"],
        "supported_surfaces": ["business"],
        "editor": {"adapter": "app-module-frame"},
        "runtime": {"adapter": "controlled-module-host"},
    },
}


_STYLE_SCHEMA = {
    "display": {"type": "string"}, "color": {"type": "string"},
    "background": {"type": "string"}, "padding": {"type": "string"},
    "margin": {"type": "string"}, "gap": {"type": "string"},
    "fontSize": {"type": "string"}, "fontWeight": {"type": "string"},
    "textAlign": {"type": "string"}, "borderRadius": {"type": "string"},
}


def _upgrade_registry() -> None:
    """Add the V2 contract without changing legacy component behavior."""
    capability_by_type = {
        "shop": ["commerce"], "survey": ["survey"], "booking": ["booking"],
        "check_in": ["check_in"], "contact": ["contacts"],
    }
    for component_type, spec in COMPONENT_REGISTRY.items():
        fields = spec.get("fields") or {}
        properties = {
            key: {"type": "boolean" if kind == "boolean" else "string", "editor": kind}
            for key, kind in fields.items()
        }
        spec.setdefault("id", f"core/{component_type}")
        spec.setdefault("namespace", "core")
        spec.setdefault("version", 2)
        spec.setdefault("kind", "capability" if component_type in capability_by_type else "primitive")
        spec.setdefault("description", spec.get("label", component_type))
        spec.setdefault("property_schema", {"type": "object", "properties": properties})
        spec.setdefault("style_schema", {"type": "object", "properties": deepcopy(_STYLE_SCHEMA)})
        spec.setdefault("slots", {})
        spec.setdefault("events", [])
        spec.setdefault("actions", [])
        spec.setdefault("data_inputs", [])
        spec.setdefault("data_outputs", [])
        spec.setdefault("allowed_parents", ["section", "repeater", "stack", "grid", "overlay", "component_instance", "root"])
        spec.setdefault("allowed_children", list((spec.get("slots") or {}).keys()) and ["*"] or [])
        spec.setdefault("responsive_support", True)
        spec.setdefault("required_capabilities", capability_by_type.get(component_type, []))
        spec.setdefault("accessibility", {"keyboard": True, "label_required": component_type in {"button", "image"}})
        spec.setdefault("editor", {"adapter": "schema-panel"})
        spec.setdefault("runtime", {"adapter": "native-html"})
        spec.setdefault("supported_surfaces", ["customer", "business", "public"])
        spec.setdefault("permissions", [])
        spec.setdefault("route_behavior", "inline")
        spec.setdefault("data_dependencies", list(spec.get("data_inputs") or []))
        spec.setdefault("migration_metadata", {"status": "native"})
        spec.setdefault("migrations", [])
        spec.setdefault("keywords", [component_type, spec.get("label", component_type), spec.get("category", "")])


_upgrade_registry()

ACTION_REGISTRY: dict[str, dict] = {
    "open_page": {"label": "Go to page", "category": "Navigation", "fields": {"target": "select", "path": "text"}},
    "show_information": {"label": "Show information", "fields": {}},
    "start_survey": {"label": "Start survey", "fields": {"survey_id": "resource"}},
    "create_booking": {"label": "Create booking", "fields": {}},
    "start_checkin": {"label": "Start check-in", "fields": {"check_in_point_id": "resource"}},
    "external_link": {"label": "Open URL", "category": "Navigation", "fields": {"url": "url"}},
    "submit_form": {"label": "Submit form to collection", "category": "Data", "fields": {"model_key": "resource", "success_message": "text", "failure_message": "text"}},
    "delete_record": {"label": "Delete record", "category": "Data", "fields": {"model_key": "resource"}},
    "navigate_to_page": {"label": "Navigate to page", "category": "Navigation", "fields": {"path": "text"}},
    "open_modal": {"label": "Open modal", "category": "Interface", "fields": {"target": "text"}},
    "set_state": {"label": "Set state", "category": "Interface", "fields": {"key": "text", "value": "text"}},
    "create_record": {"label": "Create record", "category": "Data", "fields": {"model_key": "resource"}},
    "update_record": {"label": "Update record", "category": "Data", "fields": {"model_key": "resource"}},
    "start_workflow": {"label": "Start workflow", "category": "Workflow", "fields": {"workflow_id": "resource"}},
    "show_notification": {"label": "Show notification", "category": "Interface", "fields": {"message": "text"}},
    "add_to_cart": {"label": "Add to cart", "category": "Commerce", "fields": {"item_id": "resource"}, "required_capability": "commerce", "handler_adapter": "checkout_platform"},
    "submit_feedback": {"label": "Submit feedback", "category": "Feedback", "fields": {}, "required_capability": "feedback", "handler_adapter": "feedback_platform"},
    "submit_response": {"label": "Submit survey response", "category": "Survey", "fields": {"survey_id": "resource"}, "required_capability": "survey", "handler_adapter": "qr_experience_runtime"},
    "check_in": {"label": "Check in", "category": "Check-in", "fields": {"check_in_point_id": "resource"}, "required_capability": "check_in", "handler_adapter": "checkin_platform"},
    "validate_event_pass": {"label": "Validate event pass", "category": "Events", "fields": {"event_id": "resource"}, "required_capability": "events", "handler_adapter": "event_platform"},
}

for _action_type, _action_spec in ACTION_REGISTRY.items():
    _action_spec.setdefault("id", f"core/{_action_type}")
    _action_spec.setdefault("version", 2)
    _action_spec.setdefault("category", "Advanced")
    _action_spec.setdefault("description", _action_spec["label"])
    _action_spec.setdefault("configuration_schema", {
        "type": "object",
        "properties": {
            key: {"type": "string", "editor": kind}
            for key, kind in (_action_spec.get("fields") or {}).items()
        },
    })

BLOCK_TYPES = tuple(COMPONENT_REGISTRY)
ACTION_TYPES = tuple(ACTION_REGISTRY)


def new_node_key(prefix: str = "blk") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def normalize_component(component: dict, order: int = 0) -> dict:
    component_type = component.get("type") or "text"
    if component_type not in COMPONENT_REGISTRY:
        component_type = "text"
    spec = COMPONENT_REGISTRY[component_type]
    content = deepcopy(spec["defaults"])
    incoming = component.get("content")
    if isinstance(incoming, dict):
        content.update(incoming)
    key = component.get("key") or component.get("block_key") or component.get("block_id")
    return {
        "key": str(key or new_node_key()),
        "type": component_type,
        "content": content,
        "order": int(component.get("order", order)),
    }


def normalize_action(action: dict, order: int = 0) -> dict:
    action_type = action.get("type") or "show_information"
    if action_type not in ACTION_REGISTRY:
        action_type = "show_information"
    configuration = action.get("configuration")
    return {
        "key": str(action.get("key") or action.get("action_key") or new_node_key("act")),
        "type": action_type,
        "label": str(action.get("label") or ACTION_REGISTRY[action_type]["label"]),
        "configuration": configuration if isinstance(configuration, dict) else {},
        "order": int(action.get("order", order)),
    }


def registry_payload() -> dict:
    from builder_kernel.registry import kernel

    return kernel.editor_payload()
