"""Single registry for triggers, actions, events, and components."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from builder_kernel.limits import COMPOSE_MAX_DEPTH, COMPOSE_MAX_STEPS

Handler = Callable[[dict], Any]


def _not_wired(_ctx: dict) -> None:
    raise RuntimeError("kernel handler is not wired")


class KernelRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, dict] = {}
        self._aliases: dict[str, str] = {}
        self._components: dict[str, dict] = {}
        self._triggers: dict[str, dict] = {}
        self._events: dict[str, dict] = {}
        self._contributes: dict[str, dict] = {}
        self._core_loaded = False

    def ensure_core(self) -> None:
        if self._core_loaded:
            return
        from builder_kernel.packs.core import register_core

        register_core(self)
        self._core_loaded = True

    def register_action(
        self,
        spec: dict,
        *,
        handler: Handler | None = None,
        aliases: tuple[str, ...] = (),
    ) -> None:
        action_id = str(spec["id"])
        entry = deepcopy(spec)
        entry.setdefault("version", 1)
        entry.setdefault("kind", "action")
        entry.setdefault("surfaces", ["preview", "published"])
        entry.setdefault("hosts", ["desktop", "cloud"])
        entry.setdefault("compose", None)
        entry["handler"] = handler or _not_wired
        if entry.get("compose"):
            _validate_compose(entry["compose"])
        self._actions[action_id] = entry
        short = action_id.split("/", 1)[-1]
        self._aliases[action_id] = action_id
        self._aliases[short] = action_id
        for alias in aliases:
            self._aliases[str(alias)] = action_id

    def register_component(self, spec: dict) -> None:
        component_id = str(spec["id"])
        entry = deepcopy(spec)
        entry.setdefault("kind", "component")
        entry.setdefault("surfaces", ["preview", "published"])
        entry.setdefault("hosts", ["desktop", "cloud"])
        self._components[component_id] = entry

    def register_trigger(self, spec: dict) -> None:
        trigger_id = str(spec["id"])
        entry = deepcopy(spec)
        entry.setdefault("kind", "trigger")
        self._triggers[trigger_id] = entry

    def register_event(self, spec: dict) -> None:
        event_id = str(spec["id"])
        entry = deepcopy(spec)
        entry.setdefault("kind", "event")
        self._events[event_id] = entry

    def register_contributes(self, package_id: str, contributes: dict | None) -> None:
        """Register package contribution points for editor surfaces."""
        from universal_builder_packages import normalize_contributes, validate_contributes

        package = str(package_id or "").strip()
        if not package:
            raise ValueError("package_id is required")
        errors = validate_contributes(contributes)
        if errors:
            raise ValueError(errors[0])
        self._contributes[package] = {
            "package_id": package,
            "contributes": normalize_contributes(contributes),
        }

    def resolve_action_id(self, value: str | None) -> str | None:
        self.ensure_core()
        raw = str(value or "").strip()
        if not raw:
            return None
        return self._aliases.get(raw)

    def known_action_id(self, value: str | None) -> bool:
        return self.resolve_action_id(value) is not None

    def action(self, value: str | None) -> dict | None:
        action_id = self.resolve_action_id(value)
        if not action_id:
            return None
        return self._actions[action_id]

    def editor_payload(self) -> dict:
        self.ensure_core()
        from builder_components import ACTION_REGISTRY, COMPONENT_REGISTRY
        from universal_builder_packages import CONTRIBUTES_KEYS

        contributes = {key: [] for key in CONTRIBUTES_KEYS}
        packages = []
        for package_id in sorted(self._contributes):
            entry = deepcopy(self._contributes[package_id])
            packages.append(entry)
            for key in CONTRIBUTES_KEYS:
                contributes[key].extend(entry["contributes"].get(key) or [])

        return {
            "schema_version": 2,
            "kernel_schema_version": 1,
            "components": deepcopy(COMPONENT_REGISTRY),
            "actions": deepcopy(ACTION_REGISTRY),
            "triggers": {key: {k: v for k, v in spec.items() if k != "handler"} for key, spec in self._triggers.items()},
            "events": {key: {k: v for k, v in spec.items() if k != "handler"} for key, spec in self._events.items()},
            "contributes": contributes,
            "packages": packages,
        }

    def action_ids(self) -> frozenset:
        self.ensure_core()
        return frozenset(self._actions) | frozenset(self._aliases)


def _validate_compose(steps: list) -> None:
    if not isinstance(steps, list) or not steps:
        raise ValueError("compose must be a non-empty list")
    if len(steps) > COMPOSE_MAX_STEPS:
        raise ValueError("compose exceeds max steps")
    depth = _compose_depth(steps, 0)
    if depth > COMPOSE_MAX_DEPTH:
        raise ValueError("compose exceeds max depth")


def _compose_depth(steps: list, current: int) -> int:
    deepest = current + 1
    for step in steps:
        nested = (step or {}).get("compose") if isinstance(step, dict) else None
        if nested:
            deepest = max(deepest, _compose_depth(nested, current + 1))
    return deepest


kernel = KernelRegistry()
