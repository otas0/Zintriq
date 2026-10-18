"""Unified Intermediate Representation: graph over meta descriptions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from meta.description.composite import MappingDesc, SequenceDesc, StructDesc, mapping, sequence, struct_from_items
from meta.description.types import AtomDesc, Constraint, Desc, atom, validate_desc
from meta.uir.errors import UIRError
from meta.uir.marks import strip_view

NODE_KINDS = frozenset({"literal", "reference", "record", "array", "map"})


@dataclass(frozen=True)
class UIRNode:
    id: str
    kind: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UIREdge:
    id: str
    source: str
    target: str
    label: str


@dataclass
class UIR:
    """Graph IR with a single root description node."""

    nodes: dict[str, UIRNode]
    edges: dict[str, UIREdge]
    root: str
    source: str = "mixed"

    def to_data(self) -> dict:
        return {
            "root": self.root,
            "source": self.source,
            "nodes": {
                node_id: {
                    "id": node.id,
                    "kind": node.kind,
                    "properties": dict(sorted(node.properties.items())),
                }
                for node_id, node in sorted(self.nodes.items())
            },
            "edges": {
                edge_id: {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "label": edge.label,
                }
                for edge_id, edge in sorted(self.edges.items())
            },
        }


def from_desc(node: Desc, *, source: str = "mixed") -> UIR:
    validate_desc(node)
    builder = _Builder()
    root_id = builder.add_desc(node)
    return UIR(nodes=builder.nodes, edges=builder.edges, root=root_id, source=source)


def to_desc(uir: UIR) -> Desc:
    if not uir.root or uir.root not in uir.nodes:
        raise UIRError("UIR root missing")
    return _rebuild(uir, uir.root, set())


class _Builder:
    def __init__(self) -> None:
        self.nodes: dict[str, UIRNode] = {}
        self.edges: dict[str, UIREdge] = {}
        self._n = 0
        self._e = 0

    def _nid(self) -> str:
        self._n += 1
        return f"n{self._n}"

    def _eid(self) -> str:
        self._e += 1
        return f"e{self._e}"

    def add_desc(self, node: Desc) -> str:
        if isinstance(node, AtomDesc):
            return self._add_atom(node)
        if isinstance(node, StructDesc):
            return self._add_struct(node)
        if isinstance(node, SequenceDesc):
            return self._add_sequence(node)
        if isinstance(node, MappingDesc):
            return self._add_mapping(node)
        raise UIRError(f"unsupported description form: {type(node)!r}")

    def _link(self, source: str, target: str, label: str) -> None:
        edge_id = self._eid()
        self.edges[edge_id] = UIREdge(id=edge_id, source=source, target=target, label=label)

    def _add_atom(self, node: AtomDesc) -> str:
        node_id = self._nid()
        if node.ref is not None:
            kind = "reference"
            props: dict[str, Any] = {"type": node.type_name, "ref": node.ref}
        else:
            kind = "literal"
            props = {"type": node.type_name, "has_value": node.has_value}
            if node.has_value:
                props["value"] = node.value
        if node.unit:
            props["unit"] = node.unit
        if node.constraints:
            props["constraints"] = [item.to_data() for item in node.constraints]
        self.nodes[node_id] = UIRNode(id=node_id, kind=kind, properties=props)
        return node_id

    def _add_struct(self, node: StructDesc) -> str:
        node_id = self._nid()
        self.nodes[node_id] = UIRNode(
            id=node_id,
            kind="record",
            properties={"fields": [name for name, _child in node.fields]},
        )
        for name, child in node.fields:
            child_id = self.add_desc(child)
            self._link(node_id, child_id, name)
        return node_id

    def _add_sequence(self, node: SequenceDesc) -> str:
        node_id = self._nid()
        self.nodes[node_id] = UIRNode(
            id=node_id,
            kind="array",
            properties={"length": len(node.items)},
        )
        for index, child in enumerate(node.items):
            child_id = self.add_desc(child)
            self._link(node_id, child_id, str(index))
        return node_id

    def _add_mapping(self, node: MappingDesc) -> str:
        node_id = self._nid()
        self.nodes[node_id] = UIRNode(
            id=node_id,
            kind="map",
            properties={"keys": [key for key, _child in node.entries]},
        )
        for key, child in node.entries:
            child_id = self.add_desc(child)
            self._link(node_id, child_id, key)
        return node_id


def _rebuild(uir: UIR, node_id: str, seen: set[str]) -> Desc:
    if node_id in seen:
        raise UIRError(f"cycle at {node_id!r}")
    seen.add(node_id)
    node = uir.nodes.get(node_id)
    if node is None:
        raise UIRError(f"missing node {node_id!r}")
    if node.kind not in NODE_KINDS:
        raise UIRError(f"unsupported UIR kind: {node.kind!r}")
    children = _children(uir, node_id)
    if node.kind == "literal":
        return _atom_from_props(node.properties, ref=None)
    if node.kind == "reference":
        ref = node.properties.get("ref")
        if not isinstance(ref, str):
            raise UIRError("reference node requires ref string")
        return _atom_from_props(node.properties, ref=ref)
    if node.kind == "record":
        fields = node.properties.get("fields")
        if not isinstance(fields, list):
            # Fall back to edge labels in sorted order for robustness.
            fields = sorted(children.keys())
        items = []
        for name in fields:
            if name not in children:
                raise UIRError(f"record missing field edge {name!r}")
            items.append((str(name), _rebuild(uir, children[str(name)], seen.copy())))
        return struct_from_items(items)
    if node.kind == "array":
        length = int(node.properties.get("length", len(children)))
        items = []
        for index in range(length):
            key = str(index)
            if key not in children:
                raise UIRError(f"array missing index edge {key!r}")
            items.append(_rebuild(uir, children[key], seen.copy()))
        return sequence(*items)
    if node.kind == "map":
        keys = node.properties.get("keys")
        if not isinstance(keys, list):
            keys = sorted(children.keys())
        entries = {}
        for key in keys:
            key_s = str(key)
            if key_s not in children:
                raise UIRError(f"map missing key edge {key_s!r}")
            entries[key_s] = _rebuild(uir, children[key_s], seen.copy())
        return mapping(**entries)
    raise UIRError(f"unsupported UIR kind: {node.kind!r}")


def _children(uir: UIR, node_id: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for edge in uir.edges.values():
        if edge.source != node_id:
            continue
        if edge.label in out:
            raise UIRError(f"duplicate edge label {edge.label!r} on {node_id!r}")
        out[edge.label] = edge.target
    return out


def _atom_from_props(props: dict[str, Any], *, ref: str | None) -> AtomDesc:
    # Projection-only view marks never enter Desc.
    props = strip_view(props)
    type_name = str(props.get("type") or "")
    constraints_data = props.get("constraints") or []
    constraints = tuple(Constraint.from_data(item) for item in constraints_data)
    if ref is not None:
        return atom(
            type_name,
            ref=ref,
            unit=props.get("unit"),
            constraints=constraints,
        )
    has_value = bool(props.get("has_value"))
    return atom(
        type_name,
        value=props.get("value"),
        has_value=has_value,
        unit=props.get("unit"),
        constraints=constraints,
    )


def uir_from_data(data: Any) -> UIR:
    if not isinstance(data, dict):
        raise UIRError("UIR must be an object")
    root = str(data.get("root") or "")
    source = str(data.get("source") or "mixed")
    nodes_data = data.get("nodes")
    edges_data = data.get("edges")
    if not isinstance(nodes_data, dict) or not isinstance(edges_data, dict):
        raise UIRError("UIR requires nodes and edges objects")
    nodes: dict[str, UIRNode] = {}
    for node_id, raw in nodes_data.items():
        if not isinstance(raw, dict):
            raise UIRError("node must be an object")
        kind = str(raw.get("kind") or "")
        if kind not in NODE_KINDS:
            raise UIRError(f"unsupported UIR kind: {kind!r}")
        props = raw.get("properties") or {}
        if not isinstance(props, dict):
            raise UIRError("node properties must be an object")
        nodes[str(node_id)] = UIRNode(id=str(raw.get("id") or node_id), kind=kind, properties=dict(props))
    edges: dict[str, UIREdge] = {}
    for edge_id, raw in edges_data.items():
        if not isinstance(raw, dict):
            raise UIRError("edge must be an object")
        edges[str(edge_id)] = UIREdge(
            id=str(raw.get("id") or edge_id),
            source=str(raw.get("source") or ""),
            target=str(raw.get("target") or ""),
            label=str(raw.get("label") or ""),
        )
    uir = UIR(nodes=nodes, edges=edges, root=root, source=source)
    if uir.root not in uir.nodes:
        raise UIRError("UIR root missing")
    return uir
