"""Zintriq Engine: local Play loop over scene, physics, and skin.

Same host. Not Unity.
"""

from __future__ import annotations

from typing import Any

from meta.description.composite import StructDesc
from meta.description.types import AtomDesc, Desc
from meta.runtime.kernels import scene_compile, step_physics, step_skeleton

DT = 1.0 / 60.0


def play_frame(
    scene: Desc | None = None,
    *,
    physics: Desc | None = None,
    skeleton: Desc | None = None,
    t: float = 0.0,
    dt: float = DT,
    playing: bool = True,
) -> dict[str, Any]:
    graph = scene_compile(scene) if scene is not None else {"hierarchy": [], "instances": [], "unity": False, "kind": "scene"}
    body = step_physics(physics, dt=dt) if physics is not None else None
    skin = step_skeleton(skeleton) if skeleton is not None else None
    nxt = float(t) + (float(dt) if playing else 0.0)
    prefabs = list(graph.get("instances") or [])
    return {
        "dt": float(dt),
        "engine": True,
        "physics": body,
        "playing": bool(playing),
        "prefabs": prefabs,
        "scene": graph,
        "skin": skin,
        "t": nxt,
        "unity": False,
    }


def play_session(
    scene: Desc | None = None,
    *,
    physics: Desc | None = None,
    skeleton: Desc | None = None,
    frames: int = 2,
    dt: float = DT,
) -> dict[str, Any]:
    t = 0.0
    rows = []
    for _ in range(max(1, int(frames))):
        frame = play_frame(scene, physics=physics, skeleton=skeleton, t=t, dt=dt, playing=True)
        t = float(frame["t"])
        rows.append(frame)
    return {
        "engine": True,
        "frames": rows,
        "playing": True,
        "t": t,
        "unity": False,
    }


def stop_session(frame: dict[str, Any] | None = None) -> dict[str, Any]:
    row = dict(frame or {})
    row["playing"] = False
    row["engine"] = True
    row["unity"] = False
    return row


def _part_kind(child: Desc) -> str:
    if not isinstance(child, StructDesc):
        return ""
    node = dict(child.fields).get("kind")
    if isinstance(node, AtomDesc) and node.has_value:
        return str(node.value or "")
    return ""


def play_from_system(desc: Desc, *, frames: int = 2, dt: float = DT) -> dict[str, Any]:
    from meta.instantiation.system import system_parts

    scene = desc if isinstance(desc, StructDesc) and _part_kind(desc) == "scene" else None
    physics = None
    skeleton = None
    for _key, _title, child in system_parts(desc) if isinstance(desc, StructDesc) else []:
        kind = _part_kind(child)
        if kind == "scene":
            scene = child
        elif kind == "physics.body":
            physics = child
        elif kind == "skeleton.rig":
            skeleton = child
    return play_session(scene, physics=physics, skeleton=skeleton, frames=frames, dt=dt)
