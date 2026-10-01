"""Normalized Universal Builder capability registry.

Entries point at existing platform modules.  They are integration contracts,
not copies of business logic.
"""

from __future__ import annotations

from copy import deepcopy


def _capability(identifier: str, description: str, *, module: str = "", permissions=(), components=(), actions=(), dependencies=()):
    return {
        "id": identifier,
        "version": 1,
        "description": description,
        "permissions": list(permissions),
        "components": list(components),
        "actions": list(actions),
        "data_adapters": ([{"id": f"{identifier}.records", "module": module, "mode": "adapter"}] if module else []),
        "workflow": {"triggers": [f"{identifier}.created", f"{identifier}.updated"], "actions": list(actions)},
        "runtime_adapters": ([module] if module else []),
        "configuration_schema": {"type": "object", "additionalProperties": True},
        "dependencies": list(dependencies),
    }


CAPABILITY_REGISTRY = {
    "core": _capability("core", "Projects, surfaces, documents, nodes and publishing", permissions=("builder.read", "builder.update", "builder.publish")),
    "navigation": _capability("navigation", "Pages, routes and links", actions=("open_page", "external_link"), dependencies=("core",)),
    "forms": _capability("forms", "Schema driven forms and submissions", components=("form",), actions=("submit_form",), dependencies=("core", "data")),
    "data": _capability("data", "Data models, records and bindings", components=("repeater",), dependencies=("core",)),
    "auth": _capability("auth", "Customer and business authentication", module="customer_account_platform", components=("app_shell",), dependencies=("core",)),
    "commerce": _capability("commerce", "Catalog, cart, checkout and orders", module="checkout_platform", components=("shop", "store_grid", "app_module"), actions=("add_to_cart",), dependencies=("core", "data")),
    "booking": _capability("booking", "Booking creation and operations", module="booking_platform", permissions=("booking.read", "booking.create"), components=("booking",), actions=("create_booking",), dependencies=("core", "data")),
    "survey": _capability("survey", "Survey experiences and responses", module="qr_experience_runtime", components=("survey",), actions=("start_survey",), dependencies=("core", "data")),
    "feedback": _capability("feedback", "Feedback forms and responses", module="feedback_platform", components=("survey",), actions=("submit_feedback",), dependencies=("core", "data")),
    "check_in": _capability("check_in", "Check-in points and visits", module="checkin_platform", components=("check_in",), actions=("start_checkin",), dependencies=("core",)),
    "events": _capability("events", "Events and attendee passes", module="event_platform", dependencies=("core", "data")),
    "crm": _capability("crm", "Customer relationship records", module="customer_platform", dependencies=("core", "contacts")),
    "contacts": _capability("contacts", "Contacts and customer profiles", module="contact_platform", components=("contact",), dependencies=("core", "data")),
    "analytics": _capability("analytics", "Interaction and scan analytics", module="qr_experience_analytics", dependencies=("core",)),
    "notifications": _capability("notifications", "In-product notifications", module="bos.events", dependencies=("core",)),
    "qr": _capability("qr", "QR entry points into any published surface", module="qr_experience_runtime", dependencies=("core", "analytics")),
    "payments": _capability("payments", "Payment provider integration", module="payment_connect_plugin", dependencies=("core", "commerce")),
    "workflows": _capability("workflows", "Event-triggered conditions and actions", module="bos.workflows", dependencies=("core",)),
}


def capability_payload(identifier: str | None = None):
    if identifier:
        value = CAPABILITY_REGISTRY.get(identifier)
        return deepcopy(value) if value else None
    return {key: deepcopy(value) for key, value in CAPABILITY_REGISTRY.items()}


def validate_capabilities(capabilities) -> list[str]:
    errors = []
    for identifier in capabilities or []:
        if identifier not in CAPABILITY_REGISTRY:
            errors.append(f"Unknown capability: {identifier}")
    return errors
