"""Structure systems: instantiate onto the same desktop host.

Not Autodesk, Altium, DaVinci, VS Code, Unihan, a CDN, WAN, or Unity.
The set of systems is open: any approved plugin can become a project part.
"""

from __future__ import annotations

from typing import Any, Callable

from meta.description.composite import StructDesc, struct
from meta.description.types import AtomDesc, Desc, atom
from meta.instantiation.system import child_for_part_kind, software_system, system_parts

LOOP = "plugin-project-plugin"


def tag_system(desc: StructDesc, *, form: str) -> StructDesc:
    fields = dict(desc.fields)
    fields["cdn"] = atom("bool", value=False, has_value=True)
    fields["form"] = atom("string", value=str(form or "view"), has_value=True)
    fields["loop"] = atom("string", value=LOOP, has_value=True)
    fields["unity"] = atom("bool", value=False, has_value=True)
    fields["wan"] = atom("bool", value=False, has_value=True)
    return struct(**fields)


def _sys(title: str, parts: list[tuple[str, str, str]], *, form: str) -> StructDesc:
    rows: list[tuple[str, str, Desc]] = [(key, name, child_for_part_kind(kind, title=name)) for key, name, kind in parts]
    return tag_system(software_system(title=title, parts=rows), form=form)


def skin_structure_system() -> StructDesc:
    return _sys(
        "Skin structure",
        [("skeleton", "Skeleton", "skeleton.rig"), ("scene", "Scene", "scene")],
        form="skin",
    )


def cam_structure_system() -> StructDesc:
    return _sys(
        "CAM structure",
        [("circuit", "Circuit", "circuit"), ("chip", "Chip", "chip")],
        form="cam",
    )


def grade_structure_system() -> StructDesc:
    return _sys(
        "Grade structure",
        [("film", "Film", "film.cut"), ("video", "Video", "video")],
        form="grade",
    )


def layout_structure_system() -> StructDesc:
    return _sys(
        "Layout structure",
        [("workbench", "Workbench", "os"), ("ui", "UI", "page")],
        form="layout",
    )


def cjk_index_structure_system() -> StructDesc:
    return _sys(
        "CJK index structure",
        [("text", "Text", "text"), ("data", "Data", "data.table")],
        form="search",
    )


def local_mirror_structure_system() -> StructDesc:
    return _sys(
        "Local mirror structure",
        [("document", "Catalog", "document"), ("logic", "Queue", "logic")],
        form="mirror",
    )


def sync_structure_system() -> StructDesc:
    return _sys(
        "Sync structure",
        [("federate", "Federate", "social.federate"), ("channel", "Channel", "social.channel")],
        form="sync",
    )


def unity_structure_system() -> StructDesc:
    return _sys(
        "Engine structure",
        [
            ("scene", "Scene", "scene"),
            ("skeleton", "Skeleton", "skeleton.rig"),
            ("physics", "Physics", "physics.body"),
            ("animation", "Animation", "animation"),
            ("shader", "Shader", "shader"),
            ("audio", "Audio", "audio"),
            ("level", "Level", "level"),
        ],
        form="engine",
    )


def world_structure_system() -> StructDesc:
    return _sys(
        "World structure",
        [
            ("place", "Place", "level"),
            ("scene", "Scene", "scene"),
            ("logic", "Scripts", "logic"),
            ("federate", "Replica", "social.federate"),
        ],
        form="world",
    )


def ai_suite_system() -> StructDesc:
    return _sys(
        "Local AI suite",
        [("ai", "Chat", "ai"), ("weights", "Weights", "llm.weights")],
        form="ai",
    )


def structure_catalog() -> dict[str, Callable[[], StructDesc]]:
    from meta.runtime.desktop_host import zintriq_system_desc

    return {
        "ai-suite": ai_suite_system,
        "cam": cam_structure_system,
        "cjk": cjk_index_structure_system,
        "grade": grade_structure_system,
        "layout": layout_structure_system,
        "mirror": local_mirror_structure_system,
        "skin": skin_structure_system,
        "sync": sync_structure_system,
        "unity": unity_structure_system,
        "world": world_structure_system,
        "zintriq": zintriq_system_desc,
    }


def structure_flags(desc: Desc) -> dict[str, Any]:
    if not isinstance(desc, StructDesc):
        return {"cdn": False, "unity": False, "wan": False}
    fields = dict(desc.fields)
    out = {"cdn": False, "form": "", "loop": LOOP, "unity": False, "wan": False}
    for key in out:
        node = fields.get(key)
        if isinstance(node, AtomDesc) and node.has_value:
            out[key] = node.value
    out["cdn"] = False
    out["unity"] = False
    out["wan"] = False
    out["parts"] = [key for key, _title, _child in system_parts(desc)]
    return out
