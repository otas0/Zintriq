"""Builder canvas node tree compiled from an instantiated software page/site."""

from __future__ import annotations

from typing import Any

from meta.instantiation.artifact import Artifact
from meta.instantiation.compile import description_from_artifact
from meta.instantiation.errors import InstantiationError
from meta.instantiation.page import page_blocks, site_pages
from meta.instantiation.system import flatten_system_pages
from meta.description.composite import StructDesc
from meta.description.types import AtomDesc


def _desc_title(desc, fallback: str = "") -> str:
    if isinstance(desc, StructDesc):
        node = dict(desc.fields).get("title")
        if isinstance(node, AtomDesc) and node.has_value and node.value is not None:
            return str(node.value)
    return fallback


def canvas_nodes_from_blocks(blocks: list[dict] | None, *, page_key: str, title: str) -> dict[str, Any]:
    children = []
    for index, block in enumerate(blocks or ()):
        kind = str(block.get("type") or "paragraph")
        key = str(block.get("key") or f"{page_key}-{index}")
        props = {name: value for name, value in block.items() if name not in {"type", "key"}}
        children.append({"key": key, "type": kind, "props": props, "children": []})
    return {
        "key": page_key,
        "type": "page",
        "props": {"title": title},
        "children": children,
    }


def canvas_from_desc(desc, *, page_key: str | None = None) -> dict[str, Any]:
    rows = site_pages(desc) or flatten_system_pages(desc)
    pages = []
    if rows:
        for key, title, _page in rows:
            if page_key and key != page_key:
                continue
            pages.append(
                canvas_nodes_from_blocks(page_blocks(desc, key), page_key=key, title=title)
            )
    else:
        key = page_key or "home"
        blocks = page_blocks(desc, page_key)
        pages.append(canvas_nodes_from_blocks(blocks, page_key=key, title=_desc_title(desc) or "Page"))
    return {"form": "canvas", "pages": pages}


def canvas_from_artifact(artifact: Artifact, *, page_key: str | None = None) -> dict[str, Any]:
    if not isinstance(artifact, Artifact):
        raise InstantiationError("canvas requires an artifact")
    desc = description_from_artifact(artifact)
    tree = canvas_from_desc(desc, page_key=page_key)
    tree["slug"] = artifact.slug
    tree["checksum"] = artifact.checksum
    tree["target"] = artifact.target
    return tree
