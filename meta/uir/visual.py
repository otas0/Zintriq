"""Visual tree view of UIR (positions optional; no GUI).

View marks (transform / pivot / marks) live on ``properties.view`` as a
projection overlay. Desc rebuild strips them — they are not a second document.
"""

from __future__ import annotations

from typing import Any

from meta.description.types import Desc
from meta.uir.errors import UIRError
from meta.uir.graph import UIR, from_desc, to_desc, uir_from_data
from meta.uir.marks import attach_view, strip_view


def to_visual(uir: UIR) -> dict[str, Any]:
    """Serialize UIR as a visual-friendly node/edge list."""
    data = uir.to_data()
    return {
        "form": "visual",
        "root": data["root"],
        "source": "visual",
        "nodes": [
            {
                "id": node["id"],
                "kind": node["kind"],
                "properties": _node_properties(node["properties"]),
            }
            for node in data["nodes"].values()
        ],
        "edges": [
            {
                "id": edge["id"],
                "source": edge["source"],
                "target": edge["target"],
                "label": edge["label"],
            }
            for edge in data["edges"].values()
        ],
    }


def from_visual(visual: dict[str, Any]) -> UIR:
    if not isinstance(visual, dict):
        raise UIRError("visual must be an object")
    if str(visual.get("form") or "") not in {"", "visual"}:
        raise UIRError("visual form must be visual")
    nodes_list = visual.get("nodes")
    edges_list = visual.get("edges")
    if not isinstance(nodes_list, list) or not isinstance(edges_list, list):
        raise UIRError("visual requires nodes and edges lists")
    nodes = {}
    for item in nodes_list:
        if not isinstance(item, dict) or "id" not in item:
            continue
        props = item.get("properties") or {}
        if not isinstance(props, dict):
            raise UIRError("node properties must be an object")
        cleaned = attach_view(strip_view(props), props.get("view"))
        nodes[str(item["id"])] = {
            "id": item["id"],
            "kind": item.get("kind"),
            "properties": cleaned,
        }
    edges = {str(item["id"]): item for item in edges_list if isinstance(item, dict) and "id" in item}
    return uir_from_data(
        {
            "root": visual.get("root"),
            "source": "visual",
            "nodes": nodes,
            "edges": edges,
        }
    )


def _node_properties(properties: dict[str, Any]) -> dict[str, Any]:
    props = dict(properties or {})
    if "view" in props:
        return attach_view(strip_view(props), props.get("view"))
    return props


def desc_to_visual(node: Desc) -> dict[str, Any]:
    return to_visual(from_desc(node, source="visual"))


def visual_to_desc(visual: dict[str, Any]) -> Desc:
    return to_desc(from_visual(visual))
