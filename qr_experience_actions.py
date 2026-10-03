"""QR Experience editor helpers. Builder save paths must not import this."""

from __future__ import annotations

from builder_components import ACTION_REGISTRY, new_node_key


def normalize_action(action: dict, order: int = 0) -> dict:
    """Map unknown types to show_information. QR editor only."""
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
