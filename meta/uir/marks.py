"""View marks on the UIR visual projection — not a second graph database.

Editors may attach transform / pivot / marks to visual nodes. Marks live only
on the projection (``properties.view``). Desc rebuild ignores them so the
document stays atom / struct / sequence / mapping.
"""

from __future__ import annotations

from typing import Any

from meta.uir.errors import UIRError

VIEW_KEYS = frozenset({"transform", "pivot", "marks", "type", "selected"})


def normalize_transform(raw: Any) -> dict[str, float]:
    if raw is None:
        return {"x": 0.0, "y": 0.0, "z": 0.0, "sx": 1.0, "sy": 1.0, "sz": 1.0, "rx": 0.0, "ry": 0.0, "rz": 0.0}
    if not isinstance(raw, dict):
        raise UIRError("view.transform must be an object")
    out = normalize_transform(None)
    for key in out:
        if key not in raw:
            continue
        try:
            out[key] = float(raw[key])
        except (TypeError, ValueError) as exc:
            raise UIRError(f"view.transform.{key} must be a number") from exc
    return out


def normalize_pivot(raw: Any) -> dict[str, float]:
    if raw is None:
        return {"x": 0.5, "y": 0.5, "z": 0.5}
    if not isinstance(raw, dict):
        raise UIRError("view.pivot must be an object")
    out = normalize_pivot(None)
    for key in out:
        if key not in raw:
            continue
        try:
            out[key] = float(raw[key])
        except (TypeError, ValueError) as exc:
            raise UIRError(f"view.pivot.{key} must be a number") from exc
    return out


def normalize_marks(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise UIRError("view.marks must be a list of strings")
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def normalize_view(raw: Any) -> dict[str, Any] | None:
    """Return a cleaned view block, or None when empty."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise UIRError("node view must be an object")
    view: dict[str, Any] = {}
    if "transform" in raw:
        view["transform"] = normalize_transform(raw.get("transform"))
    if "pivot" in raw:
        view["pivot"] = normalize_pivot(raw.get("pivot"))
    if "marks" in raw:
        marks = normalize_marks(raw.get("marks"))
        if marks:
            view["marks"] = marks
    if "type" in raw:
        type_name = str(raw.get("type") or "").strip()
        if type_name:
            view["type"] = type_name
    if "selected" in raw:
        view["selected"] = bool(raw.get("selected"))
    return view or None


def attach_view(properties: dict[str, Any], view: Any) -> dict[str, Any]:
    """Copy properties and attach (or drop) a normalized view block."""
    props = dict(properties or {})
    cleaned = normalize_view(view)
    if cleaned is None:
        props.pop("view", None)
    else:
        props["view"] = cleaned
    return props


def strip_view(properties: dict[str, Any]) -> dict[str, Any]:
    """Desc-facing properties without the projection-only view block."""
    props = dict(properties or {})
    props.pop("view", None)
    return props


def merge_visual_views(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Keep Desc content from ``base``; copy view marks from ``overlay`` by node id."""
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        raise UIRError("visual must be an object")
    by_id: dict[str, Any] = {}
    for item in overlay.get("nodes") or []:
        if isinstance(item, dict) and item.get("id") is not None:
            view = (item.get("properties") or {}).get("view")
            if view is not None:
                by_id[str(item["id"])] = view
    nodes = []
    for item in base.get("nodes") or []:
        if not isinstance(item, dict):
            continue
        props = dict(item.get("properties") or {})
        node_id = str(item.get("id") or "")
        if node_id in by_id:
            props = attach_view(props, by_id[node_id])
        nodes.append({**item, "properties": props})
    return {**base, "nodes": nodes}
