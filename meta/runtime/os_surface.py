"""OS surface runtime: instantiate a host layout onto local disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from meta.description import to_json
from meta.description.composite import SequenceDesc, StructDesc
from meta.description.types import AtomDesc, Desc
from meta.instantiation.errors import InstantiationError


def _atom(fields: dict, name: str) -> str:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value:
        return str(node.value if node.value is not None else "")
    return ""


def host_spec(desc: Desc) -> dict[str, Any]:
    if not isinstance(desc, StructDesc):
        raise InstantiationError("os.surface must be a struct")
    fields = dict(desc.fields)
    title = _atom(fields, "title") or "Host"
    windows: list[dict[str, str]] = []
    surfaces = fields.get("surfaces")
    if isinstance(surfaces, SequenceDesc):
        for item in surfaces.items:
            if not isinstance(item, StructDesc):
                continue
            child = dict(item.fields)
            windows.append(
                {
                    "id": _atom(child, "id") or _atom(child, "key") or f"win-{len(windows)+1}",
                    "title": _atom(child, "title") or title,
                }
            )
    if not windows:
        windows.append({"id": "main", "title": title})
    return {
        "kind": "os.surface",
        "title": title,
        "windows": windows,
    }


def apply_host(desc: Desc, *, slug: str, data_root: Path) -> dict[str, Any]:
    spec = host_spec(desc)
    folder = Path(data_root) / "os" / str(slug or "host")
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "description": json.loads(to_json(desc)),
        "host": spec,
        "slug": slug,
    }
    (folder / "surface.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def os_artifact_body(desc: Desc, slug: str | None = None) -> dict[str, Any]:
    spec = host_spec(desc)
    return {
        "description": json.loads(to_json(desc)),
        "host": spec,
        "slug": slug or "",
    }
