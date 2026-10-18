"""Minimum produce path: intent → valid Desc → instantiate.

No model required. Learning cost drops because a known seed compiles, not
because an LLM becomes the document.
"""

from __future__ import annotations

import json
from typing import Any

from meta.description import to_json
from meta.instantiation import TARGET_DESKTOP_HOST, TARGET_WEB_BUILD, instantiate
from meta.instantiation.errors import InstantiationError
from meta.instantiation.system import child_for_part_kind
from meta.runtime.world import seed_desc

HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("engine", "play", "prefab", "physics"), "engine"),
    (("world", "place", "room", "metaverse"), "world.place"),
    (("page", "site", "article", "blog"), "page"),
    (("checkout", "shop", "price"), "commerce.checkout"),
    (("channel", "chat", "message"), "social.channel"),
    (("ai", "chat", "embed"), "ai"),
    (("scene", "cube", "mesh", "camera", "3d"), "scene"),
)


def guess_kind(prompt: str = "", kind: str = "") -> str:
    wanted = str(kind or "").strip().lower()
    aliases = {
        "unity": "engine",
        "player": "engine",
        "game": "scene",
        "site": "page",
        "web": "page",
        "webpage": "page",
        "website": "page",
        "app": "engine",
        "plugin": "plugin",
        "pack": "plugin",
        "stamp": "plugin",
        "place": "world.place",
    }
    if wanted:
        return aliases.get(wanted, wanted)
    text = str(prompt or "").strip().lower()
    for keys, mapped in HINTS:
        if any(key in text for key in keys):
            return mapped
    return "scene"


def produce(
    *,
    prompt: str = "",
    kind: str = "",
    title: str = "",
    slug: str = "made",
    target: str | None = None,
) -> dict[str, Any]:
    wanted = guess_kind(prompt, kind)
    label = str(title or prompt or wanted).strip()[:80] or wanted
    compile_target = target
    if wanted == "plugin":
        from plugin_catalog import stamp_plugin

        raw_form = str(prompt or "").strip()
        kind_text = str(kind or "").strip().lower()
        if kind_text not in {"", "plugin", "pack", "stamp"}:
            raw_form = raw_form or str(kind)
        cycle = stamp_plugin(name=label, form=raw_form)
        return {
            "artifact": None,
            "code": json.dumps(cycle["pack"], ensure_ascii=False, indent=2),
            "kind": "plugin",
            "loop": cycle["loop"],
            "model": False,
            "openai": False,
            "pack": cycle["pack"],
            "prompt": str(prompt or ""),
        }
    if wanted == "engine":
        from meta.runtime.structure_systems import unity_structure_system

        desc = unity_structure_system()
        compile_target = compile_target or TARGET_DESKTOP_HOST
    elif wanted == "page":
        desc = child_for_part_kind("page", title=label)
        compile_target = compile_target or TARGET_WEB_BUILD
    else:
        try:
            desc = seed_desc(wanted, label)
        except (TypeError, ValueError) as exc:
            try:
                desc = child_for_part_kind(wanted, title=label)
            except InstantiationError as inner:
                raise InstantiationError(str(inner)) from exc
    artifact = instantiate(desc, target=compile_target, slug=slug or "made")
    return {
        "artifact": artifact,
        "code": to_json(desc),
        "kind": wanted,
        "model": False,
        "openai": False,
        "prompt": str(prompt or ""),
    }
