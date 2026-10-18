"""RGA of characters. OT ops from ``meta.collab.ot`` apply here."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from meta.collab.ot import diff_ops


def char_id(replica: str, lamport: int, index: int) -> str:
    return f"{int(lamport):010d}:{replica}:{index}"


def wrap_text(value: str, replica: str, lamport: int) -> list[dict[str, Any]]:
    chars: list[dict[str, Any]] = []
    origin = ""
    for index, ch in enumerate(str(value or "")):
        ident = char_id(replica, lamport, index)
        chars.append({"ch": ch, "deleted": False, "id": ident, "origin": origin})
        origin = ident
    return chars


def rga_order(chars: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in chars or []:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or "")
        if not ident:
            continue
        children[str(item.get("origin") or "")].append(item)
    for key in children:
        children[key].sort(key=lambda row: str(row.get("id") or ""), reverse=True)
    ordered: list[dict[str, Any]] = []

    def walk(parent: str) -> None:
        for child in children.get(parent) or []:
            ordered.append(child)
            walk(str(child.get("id") or ""))

    walk("")
    return ordered


def read_text(chars: list[dict[str, Any]] | None) -> str:
    return "".join(str(item.get("ch") or "") for item in rga_order(chars) if not item.get("deleted"))


def merge_chars(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in list(left or []) + list(right or []):
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or "")
        if not ident:
            continue
        existing = by_id.get(ident)
        if existing is None:
            by_id[ident] = {
                "ch": item.get("ch"),
                "deleted": bool(item.get("deleted")),
                "id": ident,
                "origin": str(item.get("origin") or ""),
            }
            continue
        existing["deleted"] = bool(existing.get("deleted") or item.get("deleted"))
        if not existing.get("origin") and item.get("origin"):
            existing["origin"] = str(item.get("origin") or "")
    return [by_id[key] for key in sorted(by_id)]


def apply_diff(chars: list[dict[str, Any]] | None, new_text: str, replica: str, lamport: int) -> list[dict[str, Any]]:
    items = [dict(item) for item in (chars or []) if isinstance(item, dict)]
    live = [item for item in rga_order(items) if not item.get("deleted")]
    old = "".join(str(item.get("ch") or "") for item in live)
    ops = diff_ops(old, str(new_text or ""))
    cursor = 0
    seq = 0

    def next_id() -> str:
        nonlocal seq
        ident = char_id(replica, lamport, seq)
        seq += 1
        return ident

    for op in ops:
        kind = str(op.get("op") or "")
        if kind == "retain":
            cursor += int(op.get("n") or 0)
            continue
        if kind == "delete":
            n = int(op.get("n") or 0)
            for item in live[cursor : cursor + n]:
                item["deleted"] = True
            live = live[:cursor] + live[cursor + n :]
            continue
        if kind == "insert":
            text = str(op.get("s") or "")
            origin = str(live[cursor - 1].get("id") or "") if cursor else ""
            inserted: list[dict[str, Any]] = []
            for ch in text:
                ident = next_id()
                node = {"ch": ch, "deleted": False, "id": ident, "origin": origin}
                items.append(node)
                inserted.append(node)
                origin = ident
            live = live[:cursor] + inserted + live[cursor:]
            cursor += len(inserted)
    return items
