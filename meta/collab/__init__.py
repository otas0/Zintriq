"""State-based CRDT over canonical Desc JSON.

String atoms are character RGAs updated with insert/delete OT. Other atoms
are LWW registers. Structs/maps merge by key. Sequences are an observed-remove
set of items ordered by id (lamport, replica).
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from meta.collab.text import apply_diff, merge_chars, read_text, wrap_text
from meta.description.serialize import from_data, to_data
from meta.description.types import Desc


def new_replica() -> str:
    return secrets.token_hex(8)


def empty_clock() -> dict[str, int]:
    return {}


def tick(clock: dict[str, int], replica: str) -> tuple[dict[str, int], int]:
    next_clock = dict(clock or {})
    value = int(next_clock.get(replica) or 0) + 1
    next_clock[replica] = value
    return next_clock, value


def stamp(plain: Any, replica: str, lamport: int) -> dict[str, Any]:
    return _wrap(plain, replica, lamport)


def to_plain(node: Any) -> Any:
    return _plain(node)


def merge(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any] | None:
    if left is None:
        return right
    if right is None:
        return left
    return _merge_node(left, right)


def integrate_plain(previous: dict[str, Any] | None, plain: Any, replica: str, lamport: int) -> dict[str, Any]:
    """Stamp only values that changed relative to ``previous``."""
    if previous is None:
        return stamp(plain, replica, lamport)
    return _integrate(previous, plain, replica, lamport)


def desc_to_plain(node: Desc) -> Any:
    return to_data(node)


def plain_to_desc(plain: Any) -> Desc:
    return from_data(plain)


def dump_state(*, replica: str, clock: dict[str, int], doc: dict[str, Any] | None) -> str:
    return json.dumps({"clock": clock, "doc": doc, "replica": replica}, ensure_ascii=False, sort_keys=True)


def load_state(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("collab state must be an object")
    return {
        "clock": dict(data.get("clock") or {}),
        "doc": data.get("doc"),
        "replica": str(data.get("replica") or ""),
    }


def merge_clocks(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    out = dict(left or {})
    for key, value in (right or {}).items():
        out[key] = max(int(out.get(key) or 0), int(value or 0))
    return out


def _wrap(plain: Any, replica: str, lamport: int) -> Any:
    if not isinstance(plain, dict) or "form" not in plain:
        return {"form": "raw", "lamport": lamport, "replica": replica, "value": plain}
    form = str(plain.get("form") or "")
    if form == "atom":
        node = {
            "form": "atom",
            "lamport": lamport,
            "replica": replica,
            "type": plain.get("type"),
            "value": plain.get("value"),
            "ref": plain.get("ref"),
            "unit": plain.get("unit"),
            "has_value": "value" in plain,
        }
        if _is_string_atom(plain):
            node["chars"] = wrap_text("" if plain.get("value") is None else str(plain.get("value")), replica, lamport)
        return node
    if form == "struct":
        fields = plain.get("fields") if isinstance(plain.get("fields"), dict) else {}
        return {
            "form": "struct",
            "fields": {str(name): _wrap(child, replica, lamport) for name, child in fields.items()},
        }
    if form == "sequence":
        items = plain.get("items") if isinstance(plain.get("items"), list) else []
        wrapped = []
        for index, child in enumerate(items):
            wrapped.append(
                {
                    "deleted": False,
                    "id": _item_id(replica, lamport, index),
                    "node": _wrap(child, replica, lamport),
                }
            )
        return {"form": "sequence", "items": wrapped}
    if form == "mapping":
        entries = plain.get("entries") if isinstance(plain.get("entries"), dict) else {}
        return {
            "form": "mapping",
            "entries": {str(name): _wrap(child, replica, lamport) for name, child in entries.items()},
        }
    return {"form": "raw", "lamport": lamport, "replica": replica, "value": plain}


def _plain(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    form = str(node.get("form") or "")
    if form == "atom":
        out: dict[str, Any] = {"form": "atom", "type": node.get("type") or "string"}
        if isinstance(node.get("chars"), list):
            out["value"] = read_text(node.get("chars"))
        elif node.get("has_value") or "value" in node:
            out["value"] = node.get("value")
        if node.get("ref") is not None:
            out["ref"] = node.get("ref")
        if node.get("unit"):
            out["unit"] = node.get("unit")
        return out
    if form == "struct":
        fields = node.get("fields") if isinstance(node.get("fields"), dict) else {}
        return {"form": "struct", "fields": {name: _plain(child) for name, child in fields.items()}}
    if form == "sequence":
        items = []
        for item in node.get("items") or []:
            if isinstance(item, dict) and not item.get("deleted"):
                items.append(_plain(item.get("node")))
        return {"form": "sequence", "items": items}
    if form == "mapping":
        entries = node.get("entries") if isinstance(node.get("entries"), dict) else {}
        return {"form": "mapping", "entries": {name: _plain(child) for name, child in entries.items()}}
    if form == "raw":
        return node.get("value")
    return node


def _later(a: dict[str, Any], b: dict[str, Any]) -> bool:
    la = int(a.get("lamport") or 0)
    lb = int(b.get("lamport") or 0)
    if lb != la:
        return lb > la
    return str(b.get("replica") or "") > str(a.get("replica") or "")


def _merge_node(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    lf = str(left.get("form") or "")
    rf = str(right.get("form") or "")
    if lf != rf:
        return right if _later(left, right) else left
    if lf == "atom":
        if _is_string_atom(left) or _is_string_atom(right) or isinstance(left.get("chars"), list) or isinstance(right.get("chars"), list):
            return _merge_string_atoms(left, right)
        return right if _later(left, right) else left
    if lf == "raw":
        return right if _later(left, right) else left
    if lf == "struct":
        keys = set((left.get("fields") or {}) | (right.get("fields") or {}))
        fields = {}
        for key in keys:
            a = (left.get("fields") or {}).get(key)
            b = (right.get("fields") or {}).get(key)
            if a is None:
                fields[key] = b
            elif b is None:
                fields[key] = a
            else:
                fields[key] = _merge_node(a, b)
        return {"form": "struct", "fields": fields}
    if lf == "mapping":
        keys = set((left.get("entries") or {}) | (right.get("entries") or {}))
        entries = {}
        for key in keys:
            a = (left.get("entries") or {}).get(key)
            b = (right.get("entries") or {}).get(key)
            if a is None:
                entries[key] = b
            elif b is None:
                entries[key] = a
            else:
                entries[key] = _merge_node(a, b)
        return {"form": "mapping", "entries": entries}
    if lf == "sequence":
        by_id: dict[str, dict[str, Any]] = {}
        for item in list(left.get("items") or []) + list(right.get("items") or []):
            if not isinstance(item, dict):
                continue
            ident = str(item.get("id") or "")
            if not ident:
                continue
            existing = by_id.get(ident)
            if existing is None:
                by_id[ident] = dict(item)
                continue
            existing["deleted"] = bool(existing.get("deleted") or item.get("deleted"))
            existing["node"] = _merge_node(existing.get("node") or {}, item.get("node") or {})
        items = [by_id[key] for key in sorted(by_id)]
        return {"form": "sequence", "items": items}
    return right if _later(left, right) else left


def _integrate(previous: dict[str, Any], plain: Any, replica: str, lamport: int) -> dict[str, Any]:
    form = str(previous.get("form") or "")
    if not isinstance(plain, dict) or str(plain.get("form") or "") != form:
        return _wrap(plain, replica, lamport)
    if form == "atom":
        if _is_string_atom(previous) or _is_string_atom(plain) or isinstance(previous.get("chars"), list):
            if not _is_string_atom(plain):
                return _wrap(plain, replica, lamport)
            old_chars = previous.get("chars")
            if not isinstance(old_chars, list):
                old_chars = wrap_text("" if previous.get("value") is None else str(previous.get("value")), str(previous.get("replica") or replica), int(previous.get("lamport") or 0))
            new_value = "" if plain.get("value") is None else str(plain.get("value"))
            if read_text(old_chars) == new_value and previous.get("type") == plain.get("type") and previous.get("ref") == plain.get("ref") and previous.get("unit") == plain.get("unit"):
                return previous
            node = dict(previous)
            node["lamport"] = lamport
            node["replica"] = replica
            node["type"] = plain.get("type") or previous.get("type")
            node["value"] = plain.get("value")
            node["ref"] = plain.get("ref")
            node["unit"] = plain.get("unit")
            node["has_value"] = "value" in plain
            node["chars"] = apply_diff(old_chars, new_value, replica, lamport)
            return node
        same = (
            previous.get("type") == plain.get("type")
            and previous.get("value") == plain.get("value")
            and previous.get("ref") == plain.get("ref")
            and previous.get("unit") == plain.get("unit")
        )
        if same:
            return previous
        return _wrap(plain, replica, lamport)
    if form == "struct":
        old_fields = previous.get("fields") if isinstance(previous.get("fields"), dict) else {}
        new_fields = plain.get("fields") if isinstance(plain.get("fields"), dict) else {}
        fields = {}
        for key, child in new_fields.items():
            if key in old_fields:
                fields[str(key)] = _integrate(old_fields[key], child, replica, lamport)
            else:
                fields[str(key)] = _wrap(child, replica, lamport)
        return {"form": "struct", "fields": fields}
    if form == "mapping":
        old_entries = previous.get("entries") if isinstance(previous.get("entries"), dict) else {}
        new_entries = plain.get("entries") if isinstance(plain.get("entries"), dict) else {}
        entries = {}
        for key, child in new_entries.items():
            if key in old_entries:
                entries[str(key)] = _integrate(old_entries[key], child, replica, lamport)
            else:
                entries[str(key)] = _wrap(child, replica, lamport)
        return {"form": "mapping", "entries": entries}
    if form == "sequence":
        old_items = [item for item in (previous.get("items") or []) if isinstance(item, dict) and not item.get("deleted")]
        new_items = plain.get("items") if isinstance(plain.get("items"), list) else []
        reused = []
        used = set()
        for child in new_items:
            match = None
            for item in old_items:
                ident = str(item.get("id") or "")
                if ident in used:
                    continue
                if _plain(item.get("node")) == child:
                    match = item
                    break
            if match is not None:
                used.add(str(match.get("id") or ""))
                reused.append(
                    {
                        "deleted": False,
                        "id": match.get("id"),
                        "node": _integrate(match.get("node") or {}, child, replica, lamport),
                    }
                )
            else:
                reused.append(
                    {
                        "deleted": False,
                        "id": _item_id(replica, lamport, len(reused)),
                        "node": _wrap(child, replica, lamport),
                    }
                )
        tombstones = []
        for item in previous.get("items") or []:
            if not isinstance(item, dict):
                continue
            ident = str(item.get("id") or "")
            if ident and ident not in used:
                tomb = dict(item)
                tomb["deleted"] = True
                tombstones.append(tomb)
        return {"form": "sequence", "items": tombstones + reused}
    return _wrap(plain, replica, lamport)


def _item_id(replica: str, lamport: int, index: int) -> str:
    return f"{int(lamport):010d}:{replica}:{index}"


def _is_string_atom(node: Any) -> bool:
    if not isinstance(node, dict) or str(node.get("form") or "") != "atom":
        return False
    if isinstance(node.get("chars"), list):
        return True
    typ = str(node.get("type") or "")
    if typ == "string":
        return True
    return typ in {"", "string"} and isinstance(node.get("value"), str)


def _merge_string_atoms(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    later = right if _later(left, right) else left
    left_chars = left.get("chars") if isinstance(left.get("chars"), list) else None
    right_chars = right.get("chars") if isinstance(right.get("chars"), list) else None
    if left_chars is None or right_chars is None:
        if isinstance(later.get("chars"), list):
            return dict(later)
        wrapped = dict(later)
        wrapped["chars"] = wrap_text(
            "" if later.get("value") is None else str(later.get("value")),
            str(later.get("replica") or ""),
            int(later.get("lamport") or 0),
        )
        wrapped["has_value"] = True
        wrapped["value"] = read_text(wrapped["chars"])
        return wrapped
    chars = merge_chars(left_chars, right_chars)
    return {
        "form": "atom",
        "chars": chars,
        "has_value": True,
        "lamport": later.get("lamport"),
        "ref": later.get("ref"),
        "replica": later.get("replica"),
        "type": later.get("type") or "string",
        "unit": later.get("unit"),
        "value": read_text(chars),
    }
