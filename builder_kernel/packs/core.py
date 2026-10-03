"""Built-in triggers, actions, events, and component ids."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder_kernel.registry import KernelRegistry


def register_core(registry: "KernelRegistry") -> None:
    from builder_components import ACTION_REGISTRY, COMPONENT_REGISTRY

    for component_type, spec in COMPONENT_REGISTRY.items():
        registry.register_component({
            "id": f"core/{component_type}",
            "short_id": component_type,
            "label": spec.get("label", component_type),
            "category": spec.get("category", ""),
            "required_capabilities": spec.get("required_capabilities") or [],
        })

    registry.register_trigger({"id": "core/on_click", "label": "Click"})
    registry.register_trigger({"id": "core/on_submit", "label": "Submit"})

    registry.register_event({"id": "core/record.created"})
    registry.register_event({"id": "core/record.updated"})
    registry.register_event({"id": "core/record.deleted"})

    for action_type, spec in ACTION_REGISTRY.items():
        registry.register_action(
            {
                "id": spec.get("id") or f"core/{action_type}",
                "short_id": action_type,
                "label": spec.get("label", action_type),
                "category": spec.get("category", ""),
                "required_capabilities": (
                    [spec["required_capability"]] if spec.get("required_capability") else []
                ),
                "configuration_schema": spec.get("configuration_schema") or {},
            },
            aliases=(action_type,),
        )
