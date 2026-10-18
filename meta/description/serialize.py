"""Canonical JSON round-trip for meta descriptions."""

from __future__ import annotations

import json
from typing import Any

from meta.description.composite import struct_from_items
from meta.description.errors import DescriptionError
from meta.description.types import Constraint, Desc, atom, validate_desc


def to_json(node: Desc, *, indent: int | None = None) -> str:
    validate_desc(node)
    return json.dumps(node.to_data(), ensure_ascii=False, sort_keys=True, indent=indent)


def from_json(text: str) -> Desc:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DescriptionError(f"invalid json: {exc}") from exc
    return from_data(data)


def from_data(data: Any) -> Desc:
    if not isinstance(data, dict):
        raise DescriptionError("description must be an object")
    form = str(data.get("form") or "").strip()
    if form == "atom":
        constraints = tuple(Constraint.from_data(item) for item in (data.get("constraints") or []))
        has_value = "value" in data
        return atom(
            str(data.get("type") or ""),
            value=data.get("value"),
            has_value=has_value,
            ref=data.get("ref"),
            unit=data.get("unit"),
            constraints=constraints,
        )
    if form == "struct":
        fields = data.get("fields")
        if not isinstance(fields, dict):
            raise DescriptionError("struct fields must be an object")
        items = [(str(name), from_data(child)) for name, child in fields.items()]
        items.sort(key=lambda item: item[0])
        return struct_from_items(items)
    if form == "sequence":
        items = data.get("items")
        if not isinstance(items, list):
            raise DescriptionError("sequence items must be a list")
        from meta.description.composite import sequence

        return sequence(*(from_data(child) for child in items))
    if form == "mapping":
        entries = data.get("entries")
        if not isinstance(entries, dict):
            raise DescriptionError("mapping entries must be an object")
        from meta.description.composite import mapping

        return mapping(**{str(key): from_data(child) for key, child in entries.items()})
    raise DescriptionError(f"unsupported form: {form!r}")


def to_data(node: Desc) -> dict:
    validate_desc(node)
    return node.to_data()
