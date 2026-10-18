"""Local kernels over Desc: physics, skeleton, film, B-rep, settlement, federation, weights.

These compile on the same describe → simulate → instantiate path. They are not
Unity, Autodesk, a card network, Discord, or a hosted LLM.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from meta.description.composite import SequenceDesc, StructDesc
from meta.description.types import AtomDesc, Desc
from meta.runtime.local_infer import (
    DEFAULT_MODEL,
    WeightsError,
    infer_chunks,
    infer_local,
    resolve_model_path,
)

KERNEL_KINDS = frozenset(
    {
        "animation",
        "ai",
        "audio",
        "cad.brep",
        "chain.ledger",
        "circuit",
        "chip",
        "cnc.job",
        "commerce.settle",
        "film.cut",
        "llm.weights",
        "map",
        "material",
        "model3d",
        "particle",
        "physics.body",
        "print3d.job",
        "quantum",
        "robotics.cell",
        "shader",
        "skeleton.rig",
        "social.federate",
        "spreadsheet",
        "terrain",
        "text",
        "vector",
        "bitmap",
        "level",
        "logic",
        "font",
        "document",
        "node",
        "ui",
        "scene",
        "data",
        "video",
        "vr.space",
    }
)


def _fields(desc: Desc) -> dict:
    return dict(desc.fields) if isinstance(desc, StructDesc) else {}


def _num(fields: dict, name: str, default: float = 0.0) -> float:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    return float(default)


def _text(fields: dict, name: str, default: str = "") -> str:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value and node.value is not None:
        return str(node.value)
    return default


def _bool(fields: dict, name: str, default: bool = False) -> bool:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value:
        return bool(node.value)
    return default


def _items(fields: dict, name: str) -> list:
    node = fields.get(name)
    if isinstance(node, SequenceDesc):
        return list(node.items)
    return []


def step_physics(desc: Desc, *, dt: float = 1.0 / 60.0) -> dict[str, Any]:
    fields = _fields(desc)
    vel = _num(fields, "vy", 0.0)
    pos = _num(fields, "y", 0.0)
    mass = max(_num(fields, "mass", 1.0), 0.001)
    g = _num(fields, "gravity", -9.8)
    vel = vel + g * dt
    pos = pos + vel * dt
    return {
        "ax": 0.0,
        "ay": g,
        "dt": dt,
        "kind": "physics.body",
        "mass": mass,
        "vx": _num(fields, "vx", 0.0),
        "vy": vel,
        "x": _num(fields, "x", 0.0),
        "y": pos,
        "floor": pos <= 0,
        "bounce": abs(vel) if pos <= 0 else 0.0,
    }


def step_skeleton(desc: Desc) -> dict[str, Any]:
    fields = _fields(desc)
    chain = []
    x, y = 0.0, 0.0
    heading = -math.pi / 2
    for item in _items(fields, "bones"):
        row = _fields(item) if isinstance(item, StructDesc) else {}
        length = max(_num(row, "length", 1.0), 0.01)
        angle = _num(row, "angle", 0.0) * math.pi / 180.0
        heading += angle
        x += length * math.cos(heading)
        y += length * math.sin(heading)
        chain.append(
            {
                "angle": _num(row, "angle", 0.0),
                "id": _text(row, "id") or f"bone-{len(chain)}",
                "length": length,
                "parent": _text(row, "parent"),
                "weight": _num(row, "weight", 1.0),
                "x": x,
                "y": y,
            }
        )
    reach = _num(fields, "reach", 1.0)
    verts = [(float(b["x"]), float(b["y"])) for b in chain] or [(0.0, 0.0)]
    weights = [[(i, float(b["weight"]))] for i, b in enumerate(chain)] or [[(0, 1.0)]]
    painted = paint_weights(
        weights,
        verts,
        (0.0, 0.0),
        bone=0,
        radius=_num(fields, "brush", 2.0),
        strength=_num(fields, "paint", 0.0),
    )
    if _num(fields, "paint", 0.0) <= 0:
        painted = heat_bind([(x, y, 0.0) for x, y in verts], [(x, y, 0.0) for x, y in verts], falloff=max(2.0, reach * 4.0))
    mesh3 = skin_mesh3d([(x, y, 0.0) for x, y in verts], radius=max(6.0, reach * 8.0))
    rest3 = [(x, y, 0.0) for x, y in verts]
    dual = skin_deform_dq(mesh3["vertices"], rest3, rest3, mesh3["weights"], dual=_num(fields, "dual", 0.5))
    return {
        "bind": bind_pose(rest3),
        "bones": chain,
        "dq": dual,
        "envelope": envelope_mask(mesh3["vertices"], rest3, radius=max(6.0, reach * 8.0)),
        "ik": _bool(fields, "ik", True),
        "kind": "skeleton.rig",
        "mesh": skin_mesh(verts, width=max(8.0, reach * 10.0)),
        "mesh3d": mesh3,
        "reach": reach,
        "volume": volume_preserve(dual, mesh3["vertices"], amount=_num(fields, "volume", 0.2)),
        "weights": prune_influences(
            hammer_weights(painted, bone=0) if _bool(fields, "hammer", False) else grow_weights(painted, mesh3["vertices"], bone=0, radius=_num(fields, "grow", 0.0)),
            max_influences=max(2, int(_num(fields, "influences", 4))),
        ),
        "dq8": dq_pack(rest3, rest3),
        "twist": twist_fix(dual, rest3),
        "psd": pose_space(dual, rest3, dual),
        "limits": joint_limits(chain),
        "error": skin_error(dual, mesh3["vertices"]),
        "neighbors": copy_from_neighbor(painted),
        "cluster": skin_cluster(painted),
        "blend": dual_quat_blend(mesh3["vertices"], dual, dual=_num(fields, "dual", 0.5)),
        "stretch": stretch_correct(dual, mesh3["vertices"], amount=_num(fields, "stretch", 0.1)),
        "normals": vertex_normals(mesh3["vertices"], mesh3.get("faces")),
        "matrix": bind_matrix(rest3[0], rest3[-1] if len(rest3) > 1 else rest3[0], rest3[0], rest3[-1] if len(rest3) > 1 else rest3[0]) if rest3 else [1, 0, 0, 0, 0, 0],
    }


def ccd_ik(
    joints: list[tuple[float, float]],
    target: tuple[float, float],
    *,
    iterations: int = 12,
    max_delta: float = 0.0,
) -> list[tuple[float, float]]:
    """Cyclic coordinate descent. Joints are positions; last is the effector."""
    pts = [list(p) for p in joints]
    if len(pts) < 2:
        return [tuple(p) for p in pts]
    tx, ty = target
    for _ in range(max(1, iterations)):
        for i in range(len(pts) - 2, -1, -1):
            jx, jy = pts[i]
            ex, ey = pts[-1]
            to_end = math.atan2(ey - jy, ex - jx)
            to_tgt = math.atan2(ty - jy, tx - jx)
            delta = to_tgt - to_end
            if max_delta > 0:
                cap = float(max_delta)
                delta = max(-cap, min(cap, delta))
            cos_d, sin_d = math.cos(delta), math.sin(delta)
            for k in range(i + 1, len(pts)):
                dx, dy = pts[k][0] - jx, pts[k][1] - jy
                pts[k][0] = jx + dx * cos_d - dy * sin_d
                pts[k][1] = jy + dx * sin_d + dy * cos_d
    return [(p[0], p[1]) for p in pts]


def skin_deform(
    vertices: list[tuple[float, float]],
    rest: list[tuple[float, float]],
    posed: list[tuple[float, float]],
    weights: list[list[tuple[int, float]]],
) -> list[tuple[float, float]]:
    """Linear blend skinning in bone space (2D rotation + translation)."""
    bones = max(0, min(len(rest), len(posed)) - 1)
    mats = []
    for i in range(bones):
        rx, ry = rest[i + 1][0] - rest[i][0], rest[i + 1][1] - rest[i][1]
        px, py = posed[i + 1][0] - posed[i][0], posed[i + 1][1] - posed[i][1]
        ra = math.atan2(ry, rx)
        pa = math.atan2(py, px)
        delta = pa - ra
        mats.append((math.cos(delta), math.sin(delta), posed[i][0], posed[i][1], rest[i][0], rest[i][1]))
    if not mats and posed:
        mats.append((1.0, 0.0, posed[0][0], posed[0][1], rest[0][0] if rest else 0.0, rest[0][1] if rest else 0.0))
    out: list[tuple[float, float]] = []
    for i, (vx, vy) in enumerate(vertices):
        binds = weights[i] if i < len(weights) else []
        nx, ny, wsum = 0.0, 0.0, 0.0
        for index, w in binds:
            if w <= 0 or index < 0 or index >= len(mats):
                continue
            c, s, px, py, ox, oy = mats[index]
            lx, ly = vx - ox, vy - oy
            nx += w * (px + lx * c - ly * s)
            ny += w * (py + lx * s + ly * c)
            wsum += w
        out.append((vx, vy) if wsum <= 0 else (nx / wsum, ny / wsum))
    return out


def normalize_weights(weights: list[list[tuple[int, float]]]) -> list[list[tuple[int, float]]]:
    out: list[list[tuple[int, float]]] = []
    for binds in weights:
        total = sum(max(0.0, float(w)) for _i, w in binds)
        if total <= 0:
            out.append(list(binds))
            continue
        out.append([(int(i), float(w) / total) for i, w in binds if float(w) > 0])
    return out


def paint_weights(
    weights: list[list[tuple[int, float]]],
    vertices: list[tuple[float, ...]],
    center: tuple[float, ...],
    *,
    bone: int = 0,
    radius: float = 1.0,
    strength: float = 0.25,
) -> list[list[tuple[int, float]]]:
    """Brush add on one bone in 2D or 3D, then renormalize."""
    cx, cy, cz = _xyz(center)
    rad = max(float(radius), 1e-6)
    boost = max(0.0, min(1.0, float(strength)))
    painted: list[list[tuple[int, float]]] = []
    for i, binds in enumerate(weights):
        vx, vy, vz = _xyz(vertices[i] if i < len(vertices) else (0.0, 0.0, 0.0))
        dist = math.sqrt((vx - cx) ** 2 + (vy - cy) ** 2 + (vz - cz) ** 2)
        falloff = max(0.0, 1.0 - dist / rad)
        rows = {int(b): float(w) for b, w in binds}
        if falloff > 0:
            rows[int(bone)] = rows.get(int(bone), 0.0) + boost * falloff
        painted.append(sorted(rows.items()))
    return normalize_weights(painted)


def _xyz(point: tuple[float, ...] | list[float]) -> tuple[float, float, float]:
    if not point:
        return (0.0, 0.0, 0.0)
    x = float(point[0])
    y = float(point[1]) if len(point) > 1 else 0.0
    z = float(point[2]) if len(point) > 2 else 0.0
    return (x, y, z)


def skin_mesh(
    joints: list[tuple[float, float]],
    *,
    width: float = 12.0,
) -> dict[str, Any]:
    """Ribbon mesh along a bone chain for weight painting."""
    verts: list[tuple[float, float]] = []
    faces: list[tuple[int, int, int]] = []
    weights: list[list[tuple[int, float]]] = []
    if len(joints) < 2:
        pt = joints[0] if joints else (0.0, 0.0)
        return {"faces": [], "vertices": [pt], "weights": [[(0, 1.0)]]}
    half = max(float(width), 1.0) * 0.5
    for i, (x, y) in enumerate(joints):
        nxt = joints[i + 1] if i + 1 < len(joints) else joints[i - 1]
        dx, dy = nxt[0] - x, nxt[1] - y
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length * half, dx / length * half
        verts.extend([(x + nx, y + ny), (x - nx, y - ny)])
        bone = max(0, min(i, len(joints) - 2))
        weights.extend([[(bone, 1.0)], [(bone, 1.0)]])
        if i > 0:
            a = (i - 1) * 2
            faces.append((a, a + 1, a + 2))
            faces.append((a + 1, a + 3, a + 2))
    return {"faces": faces, "vertices": verts, "weights": weights}


def skin_mesh3d(
    joints: list[tuple[float, ...]],
    *,
    radius: float = 8.0,
    rings: int = 6,
) -> dict[str, Any]:
    """Tube mesh around a 3D bone chain for weight painting."""
    pts = [_xyz(p) for p in joints]
    if len(pts) < 2:
        pt = pts[0] if pts else (0.0, 0.0, 0.0)
        return {"faces": [], "vertices": [pt], "weights": [[(0, 1.0)]]}
    rad = max(float(radius), 0.5)
    segs = max(3, int(rings))
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    weights: list[list[tuple[int, float]]] = []
    for i, (x, y, z) in enumerate(pts):
        nxt = pts[i + 1] if i + 1 < len(pts) else pts[i - 1]
        dx, dy, dz = nxt[0] - x, nxt[1] - y, nxt[2] - z
        length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        ax, ay, az = dx / length, dy / length, dz / length
        if abs(az) < 0.9:
            bx, by, bz = -ay, ax, 0.0
        else:
            bx, by, bz = 0.0, -az, ay
        blen = math.sqrt(bx * bx + by * by + bz * bz) or 1.0
        bx, by, bz = bx / blen * rad, by / blen * rad, bz / blen * rad
        cx, cy, cz = (ay * bz - az * by), (az * bx - ax * bz), (ax * by - ay * bx)
        bone = max(0, min(i, len(pts) - 2))
        base = len(verts)
        for k in range(segs):
            ang = 2 * math.pi * k / segs
            px = x + bx * math.cos(ang) + cx * math.sin(ang)
            py = y + by * math.cos(ang) + cy * math.sin(ang)
            pz = z + bz * math.cos(ang) + cz * math.sin(ang)
            verts.append((px, py, pz))
            weights.append([(bone, 1.0)])
        if i > 0:
            prev = base - segs
            for k in range(segs):
                a = prev + k
                b = prev + (k + 1) % segs
                c = base + k
                d = base + (k + 1) % segs
                faces.append((a, b, c))
                faces.append((b, d, c))
    return {"faces": faces, "vertices": verts, "weights": weights}


def skin_deform3d(
    vertices: list[tuple[float, ...]],
    rest: list[tuple[float, ...]],
    posed: list[tuple[float, ...]],
    weights: list[list[tuple[int, float]]],
) -> list[tuple[float, float, float]]:
    """3D LBS: rotate around each bone axis (Rodrigues), then translate."""
    rest3 = [_xyz(p) for p in rest]
    posed3 = [_xyz(p) for p in posed]
    bones = max(0, min(len(rest3), len(posed3)) - 1)
    frames = []
    for i in range(bones):
        r0, r1 = rest3[i], rest3[i + 1]
        p0, p1 = posed3[i], posed3[i + 1]
        frames.append((r0, _dir(r0, r1), p0, _dir(p0, p1)))
    if not frames and posed3:
        z = (0.0, 0.0, 1.0)
        origin = posed3[0]
        rest_o = rest3[0] if rest3 else (0.0, 0.0, 0.0)
        frames.append((rest_o, z, origin, z))
    out: list[tuple[float, float, float]] = []
    for i, vert in enumerate(vertices):
        vx, vy, vz = _xyz(vert)
        binds = weights[i] if i < len(weights) else []
        nx, ny, nz, wsum = 0.0, 0.0, 0.0, 0.0
        for index, w in binds:
            if w <= 0 or index < 0 or index >= len(frames):
                continue
            r0, rdir, p0, pdir = frames[index]
            lx, ly, lz = vx - r0[0], vy - r0[1], vz - r0[2]
            rx, ry, rz = _align_vector((lx, ly, lz), rdir, pdir)
            nx += w * (p0[0] + rx)
            ny += w * (p0[1] + ry)
            nz += w * (p0[2] + rz)
            wsum += w
        out.append((vx, vy, vz) if wsum <= 0 else (nx / wsum, ny / wsum, nz / wsum))
    return out


def skin_deform_dq(
    vertices: list[tuple[float, ...]],
    rest: list[tuple[float, ...]],
    posed: list[tuple[float, ...]],
    weights: list[list[tuple[int, float]]],
    *,
    dual: float = 0.5,
) -> list[tuple[float, float, float]]:
    """Blend LBS with a dual-quaternion-style bone spin. Local, not Maya."""
    lbs = skin_deform3d(vertices, rest, posed, weights)
    mix = max(0.0, min(1.0, float(dual)))
    rest3 = [_xyz(p) for p in rest]
    posed3 = [_xyz(p) for p in posed]
    out = []
    for i, vert in enumerate(vertices):
        vx, vy, vz = _xyz(vert)
        binds = weights[i] if i < len(weights) else []
        qx, qy, qz, wsum = 0.0, 0.0, 0.0, 0.0
        for index, w in binds:
            if w <= 0 or index >= max(0, len(posed3) - 1):
                continue
            r0, r1 = rest3[index], rest3[min(index + 1, len(rest3) - 1)]
            p0, p1 = posed3[index], posed3[min(index + 1, len(posed3) - 1)]
            mid_r = ((r0[0] + r1[0]) * 0.5, (r0[1] + r1[1]) * 0.5, (r0[2] + r1[2]) * 0.5)
            mid_p = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5, (p0[2] + p1[2]) * 0.5)
            rx, ry, rz = _align_vector((vx - mid_r[0], vy - mid_r[1], vz - mid_r[2]), _dir(r0, r1), _dir(p0, p1))
            qx += w * (mid_p[0] + rx)
            qy += w * (mid_p[1] + ry)
            qz += w * (mid_p[2] + rz)
            wsum += w
        dq = (vx, vy, vz) if wsum <= 0 else (qx / wsum, qy / wsum, qz / wsum)
        lx, ly, lz = lbs[i] if i < len(lbs) else dq
        out.append(((1 - mix) * lx + mix * dq[0], (1 - mix) * ly + mix * dq[1], (1 - mix) * lz + mix * dq[2]))
    return out


def copy_skin(src: list[list[tuple[int, float]]], count: int) -> list[list[tuple[int, float]]]:
    if not src:
        return [[(0, 1.0)] for _ in range(max(0, int(count)))]
    out = []
    for i in range(max(0, int(count))):
        out.append(list(src[i % len(src)]))
    return out


def influence_ramp(weight: float) -> tuple[float, float, float]:
    t = max(0.0, min(1.0, float(weight)))
    return (t, 0.2 * (1 - t), 1.0 - t)


def bind_pose(rest: list[tuple[float, ...]]) -> list[dict[str, Any]]:
    """Rest-frame per bone. Local bind, not Autodesk Skin."""
    pts = [_xyz(p) for p in rest]
    out: list[dict[str, Any]] = []
    for i in range(max(0, len(pts) - 1)):
        a, b = pts[i], pts[i + 1]
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        out.append(
            {
                "axis": _dir(a, b),
                "bone": i,
                "length": math.sqrt(dx * dx + dy * dy + dz * dz),
                "origin": a,
            }
        )
    return out


def envelope_mask(
    vertices: list[tuple[float, ...]],
    rest: list[tuple[float, ...]],
    *,
    radius: float = 8.0,
) -> list[float]:
    """Distance envelope 0..1. Not a Maya paint volume."""
    pts = [_xyz(p) for p in rest]
    rad = max(float(radius), 1e-6)
    out: list[float] = []
    for vert in vertices:
        vx, vy, vz = _xyz(vert)
        best = rad * 4.0
        if len(pts) < 2:
            if pts:
                px, py, pz = pts[0]
                best = math.sqrt((vx - px) ** 2 + (vy - py) ** 2 + (vz - pz) ** 2)
        else:
            for i in range(len(pts) - 1):
                gap = _point_seg_gap_3d((vx, vy, vz), pts[i], pts[i + 1])
                if gap < best:
                    best = gap
        out.append(max(0.0, min(1.0, 1.0 - best / rad)))
    return out


def volume_preserve(
    deformed: list[tuple[float, ...]],
    rest_verts: list[tuple[float, ...]],
    *,
    amount: float = 0.25,
) -> list[tuple[float, float, float]]:
    """Pull candy-wrapper scale toward rest radii. Local, not Maya."""
    if not deformed:
        return []
    amt = max(0.0, min(1.0, float(amount)))
    dpts = [_xyz(p) for p in deformed]
    rpts = [_xyz(p) for p in rest_verts] or dpts
    dc = tuple(sum(p[i] for p in dpts) / len(dpts) for i in range(3))
    rc = tuple(sum(p[i] for p in rpts) / len(rpts) for i in range(3))
    out: list[tuple[float, float, float]] = []
    for i, p in enumerate(dpts):
        rp = rpts[i] if i < len(rpts) else p
        rest_d = math.sqrt(sum((rp[j] - rc[j]) ** 2 for j in range(3))) or 1e-6
        posed_d = math.sqrt(sum((p[j] - dc[j]) ** 2 for j in range(3))) or 1e-6
        scale = (1.0 - amt) + amt * (rest_d / posed_d)
        out.append((dc[0] + (p[0] - dc[0]) * scale, dc[1] + (p[1] - dc[1]) * scale, dc[2] + (p[2] - dc[2]) * scale))
    return out


def hammer_weights(weights: list[list[tuple[int, float]]], *, bone: int = 0) -> list[list[tuple[int, float]]]:
    """Replace each vertex with a single bone. Local, not Autodesk Skin."""
    return [[(int(bone), 1.0)] for _ in weights]


def grow_weights(
    weights: list[list[tuple[int, float]]],
    vertices: list[tuple[float, ...]],
    *,
    bone: int = 0,
    radius: float = 0.0,
) -> list[list[tuple[int, float]]]:
    if float(radius) <= 0:
        return weights
    seeds = [i for i, binds in enumerate(weights) if any(int(b) == int(bone) and float(w) > 0.2 for b, w in binds)]
    if not seeds:
        return weights
    return paint_weights(weights, vertices, _xyz(vertices[seeds[0]] if vertices else (0, 0, 0)), bone=bone, radius=radius, strength=0.2)


def dq_pack(rest: list[tuple[float, ...]], posed: list[tuple[float, ...]]) -> list[list[float]]:
    """Eight-float dual-quaternion analog per bone. Local, not Maya."""
    rest3 = [_xyz(p) for p in rest]
    posed3 = [_xyz(p) for p in posed]
    out: list[list[float]] = []
    for i in range(max(0, min(len(rest3), len(posed3)) - 1)):
        rdir = _dir(rest3[i], rest3[i + 1])
        pdir = _dir(posed3[i], posed3[i + 1])
        out.append([rdir[0], rdir[1], rdir[2], 1.0, pdir[0], pdir[1], pdir[2], 1.0])
    return out


def twist_fix(deformed: list[tuple[float, ...]], rest: list[tuple[float, ...]], *, amount: float = 0.35) -> list[tuple[float, float, float]]:
    """Blend toward rest up-axis. Local candy-wrapper fix, not Maya."""
    amt = max(0.0, min(1.0, float(amount)))
    out = []
    for i, vert in enumerate(deformed):
        vx, vy, vz = _xyz(vert)
        rx, ry, rz = _xyz(rest[i] if i < len(rest) else vert)
        out.append(((1 - amt) * vx + amt * rx, (1 - amt) * vy + amt * ry, (1 - amt) * vz + amt * rz))
    return out


def pose_space(
    deformed: list[tuple[float, ...]],
    rest: list[tuple[float, ...]],
    posed: list[tuple[float, ...]],
) -> list[tuple[float, float, float]]:
    """Pose-space offset in rest frame. Local, not Autodesk Skin."""
    out = []
    for i, vert in enumerate(deformed):
        vx, vy, vz = _xyz(vert)
        rx, ry, rz = _xyz(rest[i] if i < len(rest) else vert)
        px, py, pz = _xyz(posed[i] if i < len(posed) else vert)
        out.append((vx + (px - rx) * 0.15, vy + (py - ry) * 0.15, vz + (pz - rz) * 0.15))
    return out


def joint_limits(bones: list[dict[str, Any]], *, lo: float = -120.0, hi: float = 120.0) -> list[dict[str, Any]]:
    rows = []
    for bone in bones:
        angle = float(bone.get("angle") or 0.0)
        rows.append({**bone, "angle": max(float(lo), min(float(hi), angle)), "clamped": angle < lo or angle > hi})
    return rows


def skin_error(deformed: list[tuple[float, ...]], rest: list[tuple[float, ...]]) -> float:
    if not deformed:
        return 0.0
    total = 0.0
    n = 0
    for i, vert in enumerate(deformed):
        vx, vy, vz = _xyz(vert)
        rx, ry, rz = _xyz(rest[i] if i < len(rest) else vert)
        total += (vx - rx) ** 2 + (vy - ry) ** 2 + (vz - rz) ** 2
        n += 1
    return math.sqrt(total / max(1, n))


def skin_cluster(weights: list[list[tuple[int, float]]]) -> list[int]:
    """Hard-assign each vertex to its strongest bone. Local cluster, not a Skin product."""
    out: list[int] = []
    for binds in weights:
        if not binds:
            out.append(0)
            continue
        out.append(max(binds, key=lambda item: float(item[1]))[0])
    return out


def dual_quat_blend(
    lbs: list[tuple[float, ...]],
    dq: list[tuple[float, ...]],
    *,
    dual: float = 0.5,
) -> list[tuple[float, float, float]]:
    t = max(0.0, min(1.0, float(dual)))
    rows: list[tuple[float, float, float]] = []
    for a, b in zip(lbs, dq):
        ax, ay, az = _xyz(a)
        bx, by, bz = _xyz(b)
        rows.append(((1.0 - t) * ax + t * bx, (1.0 - t) * ay + t * by, (1.0 - t) * az + t * bz))
    return rows


def stretch_correct(
    deformed: list[tuple[float, ...]],
    rest: list[tuple[float, ...]],
    *,
    amount: float = 0.25,
) -> list[tuple[float, float, float]]:
    t = max(0.0, min(1.0, float(amount)))
    rows: list[tuple[float, float, float]] = []
    for a, b in zip(deformed, rest):
        dx, dy, dz = _xyz(a)
        rx, ry, rz = _xyz(b)
        rows.append((dx + (rx - dx) * t, dy + (ry - dy) * t, dz + (rz - dz) * t))
    return rows


def bind_matrix(
    rest_a: tuple[float, ...],
    rest_b: tuple[float, ...],
    posed_a: tuple[float, ...],
    posed_b: tuple[float, ...],
) -> list[float]:
    rx, ry, _ = _xyz(rest_a)
    r2x, r2y, _ = _xyz(rest_b)
    px, py, _ = _xyz(posed_a)
    p2x, p2y, _ = _xyz(posed_b)
    delta = math.atan2(p2y - py, p2x - px) - math.atan2(r2y - ry, r2x - rx)
    return [math.cos(delta), math.sin(delta), px, py, rx, ry]


def vertex_normals(
    vertices: list[tuple[float, ...]],
    faces: list[tuple[int, ...]] | None = None,
) -> list[tuple[float, float, float]]:
    n = len(vertices)
    acc = [(0.0, 0.0, 0.0) for _ in range(n)]
    for face in faces or []:
        if len(face) < 3:
            continue
        a, b, c = _xyz(vertices[face[0]]), _xyz(vertices[face[1]]), _xyz(vertices[face[2]])
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        for idx in face[:3]:
            ox, oy, oz = acc[idx]
            acc[idx] = (ox + nx, oy + ny, oz + nz)
    out: list[tuple[float, float, float]] = []
    for nx, ny, nz in acc:
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        out.append((nx / length, ny / length, nz / length))
    return out


def copy_from_neighbor(weights: list[list[tuple[int, float]]]) -> list[list[tuple[int, float]]]:
    if not weights:
        return []
    out = [list(row) for row in weights]
    for i in range(1, len(out)):
        if not out[i] and out[i - 1]:
            out[i] = list(out[i - 1])
    return out


def _dir(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    return (dx / length, dy / length, dz / length)


def _align_vector(
    vec: tuple[float, float, float],
    src: tuple[float, float, float],
    dst: tuple[float, float, float],
) -> tuple[float, float, float]:
    dot = max(-1.0, min(1.0, src[0] * dst[0] + src[1] * dst[1] + src[2] * dst[2]))
    if dot > 0.9999:
        return vec
    if dot < -0.9999:
        return (-vec[0], -vec[1], -vec[2])
    ax = src[1] * dst[2] - src[2] * dst[1]
    ay = src[2] * dst[0] - src[0] * dst[2]
    az = src[0] * dst[1] - src[1] * dst[0]
    alen = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
    ax, ay, az = ax / alen, ay / alen, az / alen
    s = math.sqrt(max(0.0, 1.0 - dot * dot))
    c = dot
    ux, uy, uz = vec
    return (
        ux * c + (ay * uz - az * uy) * s + ax * (ax * ux + ay * uy + az * uz) * (1 - c),
        uy * c + (az * ux - ax * uz) * s + ay * (ax * ux + ay * uy + az * uz) * (1 - c),
        uz * c + (ax * uy - ay * ux) * s + az * (ax * ux + ay * uy + az * uz) * (1 - c),
    )


def project_orbit(
    points: list[tuple[float, ...]],
    *,
    yaw: float = 0.4,
    pitch: float = 0.3,
    scale: float = 1.0,
    cx: float = 140.0,
    cy: float = 100.0,
) -> list[tuple[float, float]]:
    """Orthographic orbit projection for the 3D paint viewport."""
    cyaw, syaw = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    out = []
    for pt in points:
        x, y, z = _xyz(pt)
        xz = x * cyaw - z * syaw
        zz = x * syaw + z * cyaw
        yz = y * cp - zz * sp
        out.append((cx + xz * scale, cy - yz * scale))
    return out


def prune_influences(weights: list[list[tuple[int, float]]], *, max_influences: int = 4) -> list[list[tuple[int, float]]]:
    cap = max(1, int(max_influences))
    trimmed = []
    for binds in weights:
        ranked = sorted(((int(i), float(w)) for i, w in binds), key=lambda row: -row[1])[:cap]
        trimmed.append(ranked)
    return normalize_weights(trimmed)


def flood_weights(weights: list[list[tuple[int, float]]], bone: int = 0) -> list[list[tuple[int, float]]]:
    return [[(int(bone), 1.0)] for _ in weights]


def lock_normalize(
    weights: list[list[tuple[int, float]]],
    locked: list[int] | None = None,
) -> list[list[tuple[int, float]]]:
    locked_set = {int(b) for b in locked or []}
    out: list[list[tuple[int, float]]] = []
    for binds in weights:
        freeze = {int(i): max(0.0, float(w)) for i, w in binds if int(i) in locked_set}
        frozen = min(1.0, sum(freeze.values()))
        rest = [(int(i), max(0.0, float(w))) for i, w in binds if int(i) not in locked_set]
        room = max(0.0, 1.0 - frozen)
        rest_n = normalize_weights([rest])[0] if rest else []
        merged = list(freeze.items()) + [(i, w * room) for i, w in rest_n]
        out.append([(i, w) for i, w in merged if w > 1e-8])
    return out


def heat_bind(
    vertices: list[tuple[float, ...]],
    joints: list[tuple[float, ...]],
    *,
    falloff: float = 8.0,
) -> list[list[tuple[int, float]]]:
    bones = max(0, len(joints) - 1)
    rad = max(float(falloff), 1e-3)
    out = []
    for vert in vertices:
        vx, vy, vz = _xyz(vert)
        binds = []
        for i in range(bones):
            a, b = _xyz(joints[i]), _xyz(joints[i + 1])
            gap = _point_seg_gap_3d((vx, vy, vz), a, b)
            w = max(0.0, 1.0 - gap / rad)
            if w > 0:
                binds.append((i, w))
        out.append(binds or [(0, 1.0)])
    return normalize_weights(out)


def smooth_weights(
    weights: list[list[tuple[int, float]]],
    vertices: list[tuple[float, ...]],
    *,
    iterations: int = 1,
    radius: float = 12.0,
) -> list[list[tuple[int, float]]]:
    current = [list(row) for row in weights]
    pts = [_xyz(v) for v in vertices]
    rad = max(float(radius), 1e-3)
    for _ in range(max(1, int(iterations))):
        nxt = []
        for i, binds in enumerate(current):
            acc: dict[int, float] = {int(b): float(w) for b, w in binds}
            px, py, pz = pts[i] if i < len(pts) else (0.0, 0.0, 0.0)
            count = 1.0
            for j, other in enumerate(pts):
                if j == i:
                    continue
                if math.sqrt((other[0] - px) ** 2 + (other[1] - py) ** 2 + (other[2] - pz) ** 2) > rad:
                    continue
                for bone, w in current[j] if j < len(current) else []:
                    acc[int(bone)] = acc.get(int(bone), 0.0) + float(w)
                count += 1.0
            nxt.append([(k, v / count) for k, v in acc.items()])
        current = nxt
    return normalize_weights(current)


def mirror_weights(
    weights: list[list[tuple[int, float]]],
    vertices: list[tuple[float, ...]],
    *,
    axis: int = 0,
    epsilon: float = 0.5,
) -> list[list[tuple[int, float]]]:
    pts = [_xyz(v) for v in vertices]
    out = [list(row) for row in weights]
    for i, p in enumerate(pts):
        target = list(p)
        target[axis] = -target[axis]
        best, dist = i, 1e9
        for j, q in enumerate(pts):
            d = math.sqrt((q[0] - target[0]) ** 2 + (q[1] - target[1]) ** 2 + (q[2] - target[2]) ** 2)
            if d < dist:
                best, dist = j, d
        if dist <= epsilon and best < len(weights):
            out[i] = list(weights[best])
    return out


def _point_seg_gap_3d(
    point: tuple[float, float, float],
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    ax, ay, az = a
    bx, by, bz = b
    px, py, pz = point
    dx, dy, dz = bx - ax, by - ay, bz - az
    length = dx * dx + dy * dy + dz * dz
    if length <= 1e-12:
        return math.sqrt((px - ax) ** 2 + (py - ay) ** 2 + (pz - az) ** 2)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy + (pz - az) * dz) / length))
    qx, qy, qz = ax + t * dx, ay + t * dy, az + t * dz
    return math.sqrt((px - qx) ** 2 + (py - qy) ** 2 + (pz - qz) ** 2)


DEFAULT_PROCESS_CARD = {
    "annular": 0.15,
    "clearance": 4.0,
    "diff_pair_gap": 0.2,
    "layers": (
        {"id": 0, "name": "F.Cu", "oz": 1.0, "type": "signal"},
        {"id": 1, "name": "B.Cu", "oz": 1.0, "type": "signal"},
    ),
    "mask_sliver": 0.1,
    "min_drill": 0.3,
    "min_width": 0.15,
    "name": "2L-FR4",
    "silk_clearance": 0.15,
}

LAYERS_4L = (
    {"id": 0, "name": "F.Cu", "oz": 1.0, "type": "signal"},
    {"id": 1, "name": "In1.Cu", "oz": 0.5, "type": "plane"},
    {"id": 2, "name": "In2.Cu", "oz": 0.5, "type": "plane"},
    {"id": 3, "name": "B.Cu", "oz": 1.0, "type": "signal"},
)


def factory_deck(name: str = "4L-FR4") -> dict[str, Any]:
    """Named fab deck. Local rules, not a vendor Gerber stackup certificate."""
    layers = LAYERS_4L if "4L" in str(name) else DEFAULT_PROCESS_CARD["layers"]
    return process_card(
        {
            "board_h": 80.0,
            "board_w": 100.0,
            "copper_to_edge": 0.25,
            "courtyard": 0.2,
            "dielectric": 0.2,
            "er": 4.5,
            "factory": True,
            "fab_notes": "local tape-out job",
            "hole_to_hole": 0.5,
            "layers": layers,
            "mask_expansion": 0.05,
            "name": name or "4L-FR4",
            "npth_to_copper": 0.3,
            "paste": 0.05,
            "silk_to_copper": 0.15,
            "target_z": 50.0,
            "tented": True,
        }
    )


def impedance_microstrip(width: float, height: float, er: float = 4.5) -> float:
    """Wheeler-style microstrip estimate. Not a field solver."""
    w = max(float(width), 1e-6)
    h = max(float(height), 1e-6)
    we = w / h + 1.25 * (0.25 + w / h)
    return 87.0 / math.sqrt(float(er) + 1.41) * math.log(5.98 * h / (0.8 * w + 1e-6) + we * 0.01)


def gerber_map(card: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    spec = process_card(card)
    rows = []
    for layer in spec.get("layers") or ():
        ident = int(layer.get("id") or 0)
        rows.append({"ext": f".g{ident}", "name": str(layer.get("name") or f"Cu{ident}"), "type": str(layer.get("type") or "signal")})
    rows.extend(
        [
            {"ext": ".gto", "name": "F.SilkS", "type": "silk"},
            {"ext": ".gts", "name": "F.Mask", "type": "mask"},
            {"ext": ".gtl", "name": "F.Cu", "type": "signal"},
            {"ext": ".drl", "name": "Drill", "type": "drill"},
            {"ext": ".gm1", "name": "Edge.Cuts", "type": "board"},
        ]
    )
    return rows


def tapeout_pack(
    traces: list[Any],
    *,
    vias: list[dict[str, Any]] | None = None,
    card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if card and (card.get("factory") or "4L" in str(card.get("name") or "")):
        spec = process_card({**factory_deck(str(card.get("name") or "4L-FR4")), **card})
    elif card:
        spec = process_card(card)
    else:
        spec = factory_deck()
    issues = route_drc(traces, vias=vias, card=spec)
    z0 = impedance_microstrip(0.2, float(spec.get("dielectric") or 0.2), float(spec.get("er") or 4.5))
    return {
        "card": spec["name"],
        "gerber": gerber_map(spec),
        "impedance": z0,
        "issues": issues,
        "layers": len(spec.get("layers") or ()),
        "notes": str(spec.get("fab_notes") or "local tape-out job"),
        "ok": not issues,
        "padstacks": [padstack(via) for via in vias or []],
        "pour": copper_pour([(0.0, 0.0), (float(spec.get("board_w") or 100), 0.0), (float(spec.get("board_w") or 100), float(spec.get("board_h") or 80)), (0.0, float(spec.get("board_h") or 80))], traces, float(spec.get("clearance") or 4)),
        "bom": bom_from_nets(traces),
        "drill": nc_drill(vias),
        "mask": [mask_expand(float(via.get("size") or via.get("drill") or 0.6), float(spec.get("mask_expansion") or 0.05)) for via in vias or []],
        "netlist": netlist(traces, vias),
        "apertures": stack_apertures(spec),
        "excellon": excellon_text(vias),
        "rs274x": gerber_rs274x("F.Cu", traces),
        "ipc": ipc_netlist(traces, vias),
        "odb": odb_job(spec, traces, vias),
        "paste": mask_expand(0.5, float(spec.get("paste") or 0.05)),
        "panel": panelize(spec, nx=1, ny=1),
        "fiducials": fiducials(spec),
        "balance": copper_balance(traces, spec),
        "ipc2581": ipc2581(spec, traces, vias),
        "stackup": stackup_mm(spec),
        "pick": pick_place(traces),
        "centroid": centroid_xy(traces),
        "dcodes": dcode_table(traces),
        "stencil": stencil_openings(vias),
        "plated": plated_hits(vias),
        "thieve": copper_thieve(spec),
        "slots": [slot_drill(0.0, 0.0, 2.0, 0.0)],
        "keepout": keepout_hits(traces, {"x": -1.0, "y": -1.0, "w": 0.5, "h": 0.5}),
    }


def dcode_table(traces: list[Any] | None = None) -> list[dict[str, float]]:
    widths = sorted({round(float((row or {}).get("width") or 0.2), 3) for row in traces or []}) or [0.2]
    return [{"d": 10 + i, "w": w} for i, w in enumerate(widths)]


def stencil_openings(vias: list[dict[str, Any]] | None = None, *, shrink: float = 0.05) -> list[dict[str, float]]:
    rows = []
    for via in vias or []:
        size = max(0.05, float(via.get("size") or via.get("drill") or 0.5) - float(shrink))
        rows.append({"size": size, "x": float(via.get("x") or 0.0), "y": float(via.get("y") or 0.0)})
    return rows


def plated_hits(vias: list[dict[str, Any]] | None = None) -> dict[str, list]:
    hits = nc_drill(vias)["hits"]
    return {"npth": [row for row in hits if not row["plated"]], "plated": [row for row in hits if row["plated"]]}


def copper_thieve(card: dict[str, Any] | None = None, *, coverage: float = 0.35) -> dict[str, float]:
    spec = process_card(card)
    area = float(spec.get("board_w") or 100) * float(spec.get("board_h") or 80)
    fill = max(0.0, min(1.0, float(coverage)))
    return {"area": area, "fill": area * fill, "kind": "thieve"}


def slot_drill(x0: float, y0: float, x1: float, y1: float, *, drill: float = 0.3) -> dict[str, Any]:
    return {"drill": float(drill), "kind": "slot", "path": [(float(x0), float(y0)), (float(x1), float(y1))]}


def keepout_hits(traces: list[Any], zone: dict[str, float] | None = None) -> list[str]:
    box = zone or {"h": 1.0, "w": 1.0, "x": 0.0, "y": 0.0}
    x0, y0 = float(box.get("x") or 0.0), float(box.get("y") or 0.0)
    x1, y1 = x0 + float(box.get("w") or 1.0), y0 + float(box.get("h") or 1.0)
    hits: list[str] = []
    for i, trace in enumerate(traces or []):
        path = (trace or {}).get("path") or []
        for pt in path:
            px, py = float(pt[0]), float(pt[1])
            if x0 <= px <= x1 and y0 <= py <= y1:
                hits.append(f"keepout:{i}")
                break
    return hits


def nc_drill(vias: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Excellon-style hit list. Local CAM analog, not Altium."""
    hits = []
    for via in vias or []:
        hits.append(
            {
                "drill": float(via.get("drill") or 0.3),
                "plated": bool(via.get("plated", True)),
                "x": float(via.get("x") or 0.0),
                "y": float(via.get("y") or 0.0),
            }
        )
    return {"count": len(hits), "hits": hits, "kind": "excellon", "units": "mm"}


def excellon_text(vias: list[dict[str, Any]] | None = None) -> str:
    lines = ["M48", "METRIC,TZ", "%"]
    for hit in nc_drill(vias)["hits"]:
        x = int(round(float(hit["x"]) * 1000))
        y = int(round(float(hit["y"]) * 1000))
        lines.append(f"X{x}Y{y}")
    lines.append("M30")
    return "\n".join(lines)


def gerber_rs274x(layer: str, traces: list[Any] | None = None) -> str:
    n = len(traces or [])
    return f"%FSLAX24Y24*%\n%MOMM*%\nG04 {layer} hits {n}*\nM02*"


def ipc_netlist(traces: list[Any], vias: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"format": "ipc-d-356", "nets": netlist(traces, vias)}


def odb_job(card: dict[str, Any] | None, traces: list[Any], vias: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    spec = process_card(card)
    return {
        "kind": "odb++",
        "layers": gerber_map(spec),
        "name": str(spec.get("name") or "job"),
        "steps": ["profile", "drill", "net"],
        "traces": len(traces or []),
        "vias": len(vias or []),
    }


def panelize(card: dict[str, Any] | None, *, nx: int = 1, ny: int = 1) -> dict[str, Any]:
    spec = process_card(card)
    cols = max(1, int(nx))
    rows = max(1, int(ny))
    return {
        "boards": cols * rows,
        "height": float(spec.get("board_h") or 80) * rows,
        "kind": "panel",
        "width": float(spec.get("board_w") or 100) * cols,
    }


def fiducials(card: dict[str, Any] | None = None) -> list[dict[str, float]]:
    spec = process_card(card)
    w = float(spec.get("board_w") or 100)
    h = float(spec.get("board_h") or 80)
    m = 1.5
    return [{"x": m, "y": m}, {"x": w - m, "y": m}, {"x": m, "y": h - m}]


def copper_balance(traces: list[Any], card: dict[str, Any] | None = None) -> dict[str, float]:
    spec = process_card(card)
    area = max(1.0, float(spec.get("board_w") or 100) * float(spec.get("board_h") or 80))
    cover = 0.0
    for row in traces or []:
        if isinstance(row, dict):
            path = row.get("path") or []
            width = float(row.get("width") or 0.2)
            for i in range(len(path) - 1):
                a, b = path[i], path[i + 1]
                cover += math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1])) * width
    return {"coverage": min(1.0, cover / area), "ok": cover / area >= 0.05}


def ipc2581(card: dict[str, Any] | None, traces: list[Any], vias: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    spec = process_card(card)
    return {"format": "ipc-2581", "layers": len(spec.get("layers") or ()), "nets": netlist(traces, vias), "rev": "C"}


def stackup_mm(card: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    spec = process_card(card)
    thick = float(spec.get("dielectric") or 0.2)
    rows = []
    for layer in spec.get("layers") or ():
        rows.append({"name": str(layer.get("name") or "Cu"), "oz": float(layer.get("oz") or 1.0), "mm": thick})
    return rows


def pick_place(traces: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for i, row in enumerate(traces or []):
        if not isinstance(row, dict):
            continue
        path = row.get("path") or [(0, 0)]
        x = sum(float(p[0]) for p in path) / max(1, len(path))
        y = sum(float(p[1]) for p in path) / max(1, len(path))
        rows.append({"i": i, "net": str(row.get("net") or i), "rot": 0.0, "x": x, "y": y})
    return rows


def centroid_xy(traces: list[Any]) -> dict[str, float]:
    pts = []
    for row in traces or []:
        path = row.get("path") if isinstance(row, dict) else row
        for pt in path or []:
            pts.append((float(pt[0]), float(pt[1])))
    if not pts:
        return {"x": 0.0, "y": 0.0}
    return {"x": sum(p[0] for p in pts) / len(pts), "y": sum(p[1] for p in pts) / len(pts)}


def mask_expand(pad_size: float, expansion: float = 0.05) -> float:
    return max(0.0, float(pad_size) + 2.0 * float(expansion))


def netlist(traces: list[Any], vias: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    nets: dict[str, int] = {}
    for row in traces or []:
        name = str(row.get("net") or "net") if isinstance(row, dict) else "net"
        nets[name] = nets.get(name, 0) + 1
    for via in vias or []:
        name = str(via.get("net") or "net")
        nets[name] = nets.get(name, 0) + 1
    return [{"net": name, "pins": count} for name, count in sorted(nets.items())]


def stack_apertures(card: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    spec = process_card(card)
    rows = []
    for i, layer in enumerate(spec.get("layers") or ()):
        rows.append(
            {
                "dcode": 10 + i,
                "layer": str(layer.get("name") or f"Cu{i}"),
                "size": float(layer.get("oz") or 1.0),
            }
        )
    return rows


def padstack(via: dict[str, Any] | None = None) -> dict[str, Any]:
    row = via if isinstance(via, dict) else {}
    drill = float(row.get("drill") or 0.3)
    size = float(row.get("size") or drill * 2)
    return {
        "annular": max(0.0, (size - drill) * 0.5),
        "drill": drill,
        "layers": (int(row.get("from") or 0), int(row.get("to") or 1)),
        "size": size,
    }


def copper_pour(
    outline: list[tuple[float, float]],
    traces: list[Any],
    clearance: float = 4.0,
) -> dict[str, Any]:
    xs = [float(p[0]) for p in outline] or [0.0]
    ys = [float(p[1]) for p in outline] or [0.0]
    return {
        "area": max(0.0, (max(xs) - min(xs)) * (max(ys) - min(ys))),
        "clearance": float(clearance),
        "keepouts": len(traces or []),
        "outline": outline,
    }


def bom_from_nets(traces: list[Any]) -> list[dict[str, Any]]:
    nets: dict[str, int] = {}
    for row in traces or []:
        if isinstance(row, dict):
            name = str(row.get("net") or "net")
        else:
            name = "net"
        nets[name] = nets.get(name, 0) + 1
    return [{"net": name, "segments": count} for name, count in sorted(nets.items())]


def diff_pair_drc(traces: list[Any], *, gap: float = 0.2) -> list[str]:
    issues = []
    rows = [row for row in traces or [] if isinstance(row, dict) and row.get("pair")]
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if a.get("pair") != b.get("pair"):
                continue
            pa = (a.get("path") or [(0, 0)])[0]
            pb = (b.get("path") or [(0, 0)])[0]
            if abs(float(pa[0]) - float(pb[0])) > gap * 20 and abs(float(pa[1]) - float(pb[1])) > gap * 20:
                issues.append(f"pair {a.get('pair')} spacing")
    return issues


def process_card(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    card = dict(DEFAULT_PROCESS_CARD)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if value is not None:
                card[key] = value
    layers = card.get("layers") or ()
    card["layers"] = tuple(layers) if not isinstance(layers, tuple) else layers
    return card


def manhattan_route(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    *,
    jog: float = 8.0,
    layer: int = 0,
) -> dict[str, Any]:
    """Two-bend Manhattan route on a named copper layer."""
    if abs(ax - bx) < 1e-6 or abs(ay - by) < 1e-6:
        path = [(ax, ay), (bx, by)]
    elif abs(ay - by) > jog:
        mid_x = ax + (bx - ax) * 0.5
        path = [(ax, ay), (mid_x, ay), (mid_x, by), (bx, by)]
    else:
        path = [(ax, ay), (ax, by), (bx, by)]
    return {"layer": int(layer), "path": path}


def route_drc(
    traces: list[Any],
    *,
    min_gap: float = 4.0,
    min_width: float = 0.0,
    vias: list[dict[str, Any]] | None = None,
    card: dict[str, Any] | None = None,
) -> list[str]:
    """Process-card DRC: clearance, width, drill, annular, mask sliver. Not a foundry tape-out."""
    spec = process_card(card) if card else {}
    gap = float(spec.get("clearance") or min_gap)
    width_min = float(spec.get("min_width") if spec.get("min_width") is not None else min_width)
    drill_min = float(spec.get("min_drill") or 0.0)
    annular = float(spec.get("annular") or 0.0)
    mask = float(spec.get("mask_sliver") or 0.0)
    issues = []
    layer_ids = {int(row.get("id") or i) for i, row in enumerate(spec.get("layers") or ())} if spec else set()
    segs = []
    for ti, row in enumerate(traces):
        if isinstance(row, dict):
            layer = int(row.get("layer") or 0)
            path = list(row.get("path") or [])
            width = float(row.get("width") or 0.0)
            net = str(row.get("net") or ti)
        else:
            layer = 0
            path = list(row)
            width = 0.0
            net = str(ti)
        if layer_ids and layer not in layer_ids:
            issues.append(f"net {net} layer {layer} missing from stackup")
        if width_min and width and width + 1e-9 < width_min:
            issues.append(f"net {net} width {width} below {width_min}")
        for i in range(len(path) - 1):
            segs.append((ti, layer, net, path[i], path[i + 1], width))
    for i, (a_t, a_l, a_n, a0, a1, _aw) in enumerate(segs):
        for b_t, b_l, b_n, b0, b1, _bw in segs[i + 1 :]:
            if a_t == b_t or a_l != b_l or a_n == b_n:
                continue
            if _seg_gap(a0, a1, b0, b1) < gap:
                issues.append(f"layer {a_l} nets {a_n}/{b_n} closer than {gap}")
    for via in vias or []:
        vx, vy = float(via.get("x") or 0.0), float(via.get("y") or 0.0)
        vnet = str(via.get("net") or "")
        lo = int(via.get("from") or via.get("layer") or 0)
        hi = int(via.get("to") or lo)
        drill = float(via.get("drill") or 0.0)
        size = float(via.get("size") or drill)
        if drill_min and drill and drill + 1e-9 < drill_min:
            issues.append(f"via {vnet} drill {drill} below {drill_min}")
        if annular and size and drill and (size - drill) / 2 + 1e-9 < annular:
            issues.append(f"via {vnet} annular ring below {annular}")
        if mask and size and size < mask:
            issues.append(f"via {vnet} mask sliver")
        for _ti, layer, net, a0, a1, _w in segs:
            if net == vnet:
                continue
            if layer < min(lo, hi) or layer > max(lo, hi):
                continue
            if _point_seg_gap((vx, vy), a0, a1) < gap:
                issues.append(f"via {vnet} too close to net {net} on layer {layer}")
    for i, va in enumerate(vias or []):
        for vb in (vias or [])[i + 1 :]:
            sameNet = str(va.get("net") or "") == str(vb.get("net") or "")
            dx = abs(float(va.get("x") or 0) - float(vb.get("x") or 0))
            dy = abs(float(va.get("y") or 0) - float(vb.get("y") or 0))
            if not sameNet and dx < gap and dy < gap:
                issues.append("vias shorted")
            hole = float(spec.get("hole_to_hole") or 0.0)
            if hole:
                dx = float(va.get("x") or 0) - float(vb.get("x") or 0)
                dy = float(va.get("y") or 0) - float(vb.get("y") or 0)
                da = (float(va.get("drill") or 0) + float(vb.get("drill") or 0)) / 2
                if math.hypot(dx, dy) - da + 1e-9 < hole:
                    issues.append("hole-to-hole below deck")
    edge = float(spec.get("copper_to_edge") or 0.0)
    board_w = float(spec.get("board_w") or 0.0)
    board_h = float(spec.get("board_h") or 0.0)
    if edge and board_w and board_h:
        for _ti, _l, net, a0, a1, _w in segs:
            for pt in (a0, a1):
                x, y = float(pt[0]), float(pt[1])
                if x < edge or y < edge or x > board_w - edge or y > board_h - edge:
                    issues.append(f"net {net} copper-to-edge")
                    break
    target_z = float(spec.get("target_z") or 0.0)
    dielectric = float(spec.get("dielectric") or 0.0)
    if target_z and dielectric:
        for _ti, _l, net, _a0, _a1, width in segs:
            if not width:
                continue
            z0 = impedance_microstrip(width, dielectric, float(spec.get("er") or 4.5))
            if abs(z0 - target_z) > 15.0:
                issues.append(f"net {net} impedance {z0:.0f} vs {target_z:.0f}")
    expansion = float(spec.get("mask_expansion") or 0.0)
    if expansion and vias:
        for via in vias:
            size = float(via.get("size") or via.get("drill") or 0.0)
            if size and size < expansion * 2:
                issues.append("mask expansion swallows pad")
                break
    return issues


def _seg_gap(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
) -> float:
    ax0, ay0 = a0
    ax1, ay1 = a1
    bx0, by0 = b0
    bx1, by1 = b1
    if abs(ay0 - ay1) < 1e-6 and abs(by0 - by1) < 1e-6:
        if max(min(ax0, ax1), min(bx0, bx1)) <= min(max(ax0, ax1), max(bx0, bx1)):
            return abs(ay0 - by0)
        return min(abs(ax0 - bx0), abs(ax0 - bx1), abs(ax1 - bx0), abs(ax1 - bx1))
    if abs(ax0 - ax1) < 1e-6 and abs(bx0 - bx1) < 1e-6:
        if max(min(ay0, ay1), min(by0, by1)) <= min(max(ay0, ay1), max(by0, by1)):
            return abs(ax0 - bx0)
        return min(abs(ay0 - by0), abs(ay0 - by1), abs(ay1 - by0), abs(ay1 - by1))
    return 99.0


def _point_seg_gap(point: tuple[float, float], a0: tuple[float, float], a1: tuple[float, float]) -> float:
    px, py = point
    ax, ay = a0
    bx, by = a1
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def mix_audio(clips: list[dict[str, Any]], playhead: float, *, limiter: float = 1.0) -> dict[str, Any]:
    """Bus mix with 3-band EQ and peak limiter. Local preview, not a console."""
    active: list[dict[str, Any]] = []
    level = 0.0
    pan = 0.0
    buses: dict[str, float] = {}
    for clip in clips:
        start = float(clip.get("in") or clip.get("offset") or 0.0)
        dur = float(clip.get("duration") or 1.0)
        if clip.get("mute"):
            continue
        if not (start <= playhead < start + dur):
            continue
        gain = float(clip.get("gain") if clip.get("gain") is not None else 1.0)
        eq = 1.0 + 0.15 * float(clip.get("low") or 0.0) + 0.1 * float(clip.get("mid") or 0.0) + 0.15 * float(clip.get("high") or 0.0)
        send = gain * max(0.0, eq)
        p = float(clip.get("pan") or 0.0)
        bus = str(clip.get("bus") or "master")
        buses[bus] = buses.get(bus, 0.0) + send
        level += send
        pan += p * send
        active.append({"bus": bus, "clip": str(clip.get("clip") or "a"), "gain": send, "pan": p})
    peak = max(buses.values()) if buses else level
    limit = max(float(limiter), 1e-6)
    scale = limit / peak if peak > limit else 1.0
    level *= scale
    for name in list(buses):
        buses[name] *= scale
    if level:
        pan /= level if scale == 1.0 else (level / scale if scale else 1.0)
        if scale != 1.0 and level:
            pan = pan  # already weighted before scale
    return {
        "active": active,
        "buses": {k: round(v, 6) for k, v in buses.items()},
        "level": round(min(level, limit), 6),
        "limited": scale < 1.0,
        "pan": round(pan, 6),
    }


def grade_frame(
    rgb: tuple[float, float, float],
    *,
    lift: float = 0.0,
    gamma: float = 1.0,
    gain: float = 1.0,
    sat: float = 1.0,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    contrast: float = 1.0,
    hue: float = 0.0,
    temp: float = 0.0,
    tint: float = 0.0,
    lift_rgb: tuple[float, float, float] = (0.0, 0.0, 0.0),
    gamma_rgb: tuple[float, float, float] = (1.0, 1.0, 1.0),
    gain_rgb: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> tuple[float, float, float]:
    """Primaries wheels + offset/contrast/hue/temp. Local preview, not DaVinci Resolve."""
    gma = max(float(gamma), 1e-6)
    out = []
    for i, ch in enumerate(rgb):
        val = (float(ch) + float(lift) + float(lift_rgb[i]) + float(offset[i])) * float(gain) * float(gain_rgb[i])
        val = max(0.0, val) ** (1.0 / (gma * max(float(gamma_rgb[i]), 1e-6)))
        mid = val - 0.5
        val = 0.5 + mid * float(contrast)
        out.append(val)
    r, g, b = out[0], out[1], out[2]
    r += float(temp) * 0.04
    b -= float(temp) * 0.04
    g += float(tint) * 0.03
    angle = float(hue) * math.pi / 180.0
    cos_h, sin_h = math.cos(angle), math.sin(angle)
    y = 0.299 * r + 0.587 * g + 0.114 * b
    i = 0.596 * r - 0.274 * g - 0.322 * b
    q = 0.211 * r - 0.523 * g + 0.312 * b
    i2 = i * cos_h - q * sin_h
    q2 = i * sin_h + q * cos_h
    r = y + 0.956 * i2 + 0.621 * q2
    g = y - 0.272 * i2 - 0.647 * q2
    b = y - 1.107 * i2 + 1.704 * q2
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    s = float(sat)
    graded = tuple(max(0.0, min(1.0, luma + (c - luma) * s)) for c in (r, g, b))
    return (float(graded[0]), float(graded[1]), float(graded[2]))


def lut_1d(rgb: tuple[float, float, float], table: list | None = None) -> tuple[float, float, float]:
    """Piecewise 1D LUT. Not a cube LUT finishing suite."""
    raw = table if isinstance(table, list) and table else [(0.0, 0.0), (1.0, 1.0)]
    stops = []
    for row in raw:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            stops.append((float(row[0]), float(row[1])))
    if not stops:
        stops = [(0.0, 0.0), (1.0, 1.0)]
    stops.sort(key=lambda item: item[0])

    def samp(x: float) -> float:
        val = max(0.0, min(1.0, float(x)))
        for i in range(len(stops) - 1):
            a, av = stops[i]
            b, bv = stops[i + 1]
            if val <= b or i == len(stops) - 2:
                t = 0.0 if abs(b - a) < 1e-9 else (val - a) / (b - a)
                return av + t * (bv - av)
        return stops[-1][1]

    return tuple(max(0.0, min(1.0, samp(ch))) for ch in rgb)


def lut_rgb(
    rgb: tuple[float, float, float],
    r_table: list | None = None,
    g_table: list | None = None,
    b_table: list | None = None,
) -> tuple[float, float, float]:
    """Per-channel 1D LUTs. Not a cube LUT suite."""
    return (
        lut_1d((rgb[0], rgb[0], rgb[0]), r_table)[0],
        lut_1d((rgb[1], rgb[1], rgb[1]), g_table)[0],
        lut_1d((rgb[2], rgb[2], rgb[2]), b_table)[0],
    )


def stills_wipe(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
    amount: float = 0.5,
) -> tuple[float, float, float]:
    t = max(0.0, min(1.0, float(amount)))
    return tuple((1.0 - t) * a + t * b for a, b in zip(left, right))


def aces_curve(rgb: tuple[float, float, float], *, exposure: float = 0.0) -> tuple[float, float, float]:
    """Simple filmic curve. Not ACES or DaVinci."""
    gain = 2.0 ** float(exposure)
    out = []
    for ch in rgb:
        x = max(0.0, float(ch) * gain)
        out.append(max(0.0, min(1.0, x / (x + 0.18) * 1.05)))
    return (out[0], out[1], out[2])


def split_screen(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
    *,
    side: str = "left",
) -> tuple[float, float, float]:
    return left if str(side) != "right" else right


def grade_cache(rgb: tuple[float, float, float], nodes: list[dict[str, Any]] | None) -> dict[str, Any]:
    body = json.dumps({"rgb": list(rgb), "nodes": nodes or []}, sort_keys=True, default=str)
    return {"hash": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16], "rgb": list(grade_graph(rgb, nodes))}


def false_color(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    y = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    return (max(0.0, min(1.0, y * 2)), max(0.0, min(1.0, 1.0 - abs(y - 0.5) * 2)), max(0.0, min(1.0, 1.0 - y)))


def log_osc(samples: list[tuple[float, float, float]]) -> list[float]:
    rows = []
    for rgb in samples:
        y = max(1e-6, 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])
        rows.append(math.log10(y))
    return rows


def grade_graph(rgb: tuple[float, float, float], nodes: list[dict[str, Any]] | None) -> tuple[float, float, float]:
    """Apply a serial grade node graph. Local, not a finishing suite."""
    color = rgb
    for node in nodes or []:
        if node.get("mute") or node.get("bypass"):
            continue
        op = str(node.get("op") or node.get("kind") or "gain")
        if op == "parallel":
            amount = max(0.0, min(1.0, float(node.get("value") or 0.5)))
            other = grade_frame(rgb, gain=float(node.get("gain") or 1.0), sat=float(node.get("sat") or 1.0))
            color = tuple((1.0 - amount) * a + amount * b for a, b in zip(color, other))
        elif op == "lift":
            color = grade_frame(color, lift=float(node.get("value") or 0.0))
        elif op == "gamma":
            color = grade_frame(color, gamma=float(node.get("value") or 1.0))
        elif op == "gain":
            color = grade_frame(color, gain=float(node.get("value") or 1.0))
        elif op == "sat":
            color = grade_frame(color, sat=float(node.get("value") or 1.0))
        elif op == "hue":
            color = grade_frame(color, hue=float(node.get("value") or 0.0))
        elif op == "contrast":
            color = grade_frame(color, contrast=float(node.get("value") or 1.0))
        elif op == "temp":
            color = grade_frame(color, temp=float(node.get("value") or 0.0))
        elif op == "cdl":
            color = apply_cdl(
                color,
                slope=float(node.get("slope") or node.get("value") or 1.0),
                offset=float(node.get("offset") or 0.0),
                power=float(node.get("power") or 1.0),
            )
        elif op == "mix":
            amount = max(0.0, min(1.0, float(node.get("value") or 0.5)))
            other = grade_frame(rgb, gain=float(node.get("gain") or 1.0), sat=float(node.get("sat") or 1.0))
            color = tuple((1.0 - amount) * a + amount * b for a, b in zip(color, other))
        elif op == "lut":
            color = lut_1d(color, node.get("table"))
        elif op == "lutrgb":
            color = lut_rgb(color, node.get("r"), node.get("g"), node.get("b"))
        elif op == "wipe":
            other = grade_frame(rgb, gain=float(node.get("gain") or 1.0))
            color = stills_wipe(color, other, float(node.get("value") or 0.5))
        elif op == "aces":
            color = aces_curve(color, exposure=float(node.get("value") or 0.0))
        elif op == "split":
            color = split_screen(color, rgb, side=str(node.get("side") or "left"))
        elif op == "rec709":
            color = rec709_encode(color) if str(node.get("dir") or "encode") != "decode" else rec709_decode(color)
        elif op == "roll":
            color = highlight_roll(color, knee=float(node.get("knee") or 0.8), amount=float(node.get("value") or 0.4))
        elif op == "qualifier" and not qualifier_hit(rgb, node):
            break
    return color


def grade_dag(rgb: tuple[float, float, float], nodes: list[dict[str, Any]] | None) -> tuple[float, float, float]:
    """Node graph with named inputs. Local, not DaVinci."""
    by_id: dict[str, tuple[float, float, float]] = {"src": rgb}
    color = rgb
    for i, node in enumerate(nodes or []):
        ident = str(node.get("id") or f"n{i}")
        src = by_id.get(str(node.get("input") or "src"), color)
        color = grade_graph(src, [node])
        by_id[ident] = color
    return color


def grade_stills(rgb: tuple[float, float, float], stills: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows = []
    for still in stills or []:
        graded = grade_graph(rgb, still.get("nodes") if isinstance(still.get("nodes"), list) else [{"op": "gain", "value": float(still.get("gain") or 1.0)}])
        rows.append({"id": str(still.get("id") or "still"), "rgb": list(graded)})
    return rows


def apply_cdl(
    rgb: tuple[float, float, float],
    *,
    slope: float = 1.0,
    offset: float = 0.0,
    power: float = 1.0,
) -> tuple[float, float, float]:
    pwr = max(float(power), 1e-6)
    out = []
    for ch in rgb:
        val = max(0.0, float(ch) * float(slope) + float(offset))
        out.append(max(0.0, min(1.0, val ** (1.0 / pwr))))
    return (out[0], out[1], out[2])


def qualifier_hit(rgb: tuple[float, float, float], node: dict[str, Any]) -> bool:
    r, g, b = rgb
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    sat = max(abs(r - y), abs(g - y), abs(b - y))
    hue = math.degrees(math.atan2(b - y, r - y)) % 360.0
    if node.get("hue_lo") is not None and hue < float(node.get("hue_lo") or 0):
        return False
    if node.get("hue_hi") is not None and hue > float(node.get("hue_hi") or 360):
        return False
    if node.get("sat_lo") is not None and sat < float(node.get("sat_lo") or 0):
        return False
    if node.get("lum_lo") is not None and y < float(node.get("lum_lo") or 0):
        return False
    return True


def rgb_parade(samples: list[tuple[float, float, float]]) -> dict[str, list[float]]:
    r = [row[0] for row in samples]
    g = [row[1] for row in samples]
    b = [row[2] for row in samples]
    return {"b": b, "g": g, "r": r}


def histogram(samples: list[tuple[float, float, float]], *, bins: int = 16) -> list[int]:
    n = max(4, int(bins))
    counts = [0] * n
    for rgb in samples:
        y = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
        idx = min(n - 1, max(0, int(y * n)))
        counts[idx] += 1
    return counts


def waveform(samples: list[tuple[float, float, float]]) -> list[dict[str, float]]:
    rows = []
    for rgb in samples:
        r, g, b = rgb
        rows.append({"b": b, "g": g, "r": r, "y": 0.2126 * r + 0.7152 * g + 0.0722 * b})
    return rows


def vectorscope(rgb: tuple[float, float, float]) -> dict[str, float]:
    r, g, b = rgb
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return {"u": r - y, "v": b - y, "y": y}


def rec709_encode(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    def enc(ch: float) -> float:
        val = max(0.0, min(1.0, float(ch)))
        return 12.92 * val if val < 0.018 else 1.099 * (val ** 0.45) - 0.099

    return (enc(rgb[0]), enc(rgb[1]), enc(rgb[2]))


def rec709_decode(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    def dec(ch: float) -> float:
        val = max(0.0, min(1.0, float(ch)))
        return val / 12.92 if val <= 0.081 else ((val + 0.099) / 1.099) ** (1.0 / 0.45)

    return (dec(rgb[0]), dec(rgb[1]), dec(rgb[2]))


def highlight_roll(
    rgb: tuple[float, float, float],
    *,
    knee: float = 0.8,
    amount: float = 0.4,
) -> tuple[float, float, float]:
    k = max(0.0, min(1.0, float(knee)))
    t = max(0.0, min(1.0, float(amount)))
    out = []
    for ch in rgb:
        val = max(0.0, float(ch))
        if val > k:
            over = val - k
            val = k + over * (1.0 - t)
        out.append(max(0.0, min(1.0, val)))
    return (out[0], out[1], out[2])


def vectorscope_polar(rgb: tuple[float, float, float]) -> dict[str, float]:
    row = vectorscope(rgb)
    return {"r": math.hypot(row["u"], row["v"]), "theta": math.degrees(math.atan2(row["v"], row["u"])), "y": row["y"]}


def assemble_film(desc: Desc) -> dict[str, Any]:
    fields = _fields(desc)
    shots = []
    t = 0.0
    for item in _items(fields, "shots"):
        row = _fields(item) if isinstance(item, StructDesc) else {}
        start = _num(row, "in", t)
        end = _num(row, "out", 0.0)
        dur = _num(row, "duration", 0.0)
        if end > start:
            dur = end - start
        dur = max(dur if dur else 1.0, 0.01)
        track = int(_num(row, "track", 1))
        shots.append(
            {
                "at": start if start else t,
                "clip": _text(row, "clip") or "shot",
                "duration": dur,
                "in": start,
                "out": start + dur,
                "track": max(1, track),
            }
        )
        t = max(t, start + dur)
    playhead = _num(fields, "playhead", 0.0)
    active = None
    for shot in shots:
        if shot["in"] <= playhead < shot["out"]:
            active = shot["clip"]
            break
    transitions = []
    for item in _items(fields, "transitions"):
        row = _fields(item) if isinstance(item, StructDesc) else {}
        transitions.append(
            {
                "at": _num(row, "at", 0.0),
                "duration": max(_num(row, "duration", 0.2), 0.01),
                "kind": _text(row, "kind") or "cut",
            }
        )
    audio = []
    for item in _items(fields, "audio"):
        row = _fields(item) if isinstance(item, StructDesc) else {}
        audio.append(
            {
                "clip": _text(row, "clip") or "a",
                "duration": max(_num(row, "duration", 1.0), 0.01),
                "gain": _num(row, "gain", 1.0),
                "in": _num(row, "in", 0.0),
                "mute": _bool(row, "mute", False),
                "offset": _num(row, "offset", 0.0),
                "pan": _num(row, "pan", 0.0),
            }
        )
    rgb = (
        _num(fields, "lift", 0.0),
        _num(fields, "gamma", 1.0),
        _num(fields, "gain", 1.0),
    )
    mix = mix_audio(audio, playhead, limiter=_num(fields, "limiter", 1.0))
    grade = grade_frame(
        (0.5, 0.5, 0.5),
        lift=rgb[0],
        gamma=rgb[1],
        gain=rgb[2],
        sat=_num(fields, "sat", 1.0),
        contrast=_num(fields, "contrast", 1.0),
        hue=_num(fields, "hue", 0.0),
        temp=_num(fields, "temp", 0.0),
        tint=_num(fields, "tint", 0.0),
    )
    razor_at = _num(fields, "razor_at", -1.0)
    razored = razor_shot(shots, razor_at) if razor_at >= 0 else list(shots)
    cache = grade_cache(grade, [{"op": "cdl", "slope": 1.0}])
    return {
        "active": active,
        "audio": audio,
        "duration": max(t, _num(fields, "duration", t)),
        "grade": {"b": grade[2], "g": grade[1], "r": grade[0]},
        "graph": list(grade_graph(grade, [{"op": "cdl", "slope": 1.0, "offset": 0.0, "power": 1.0}, {"op": "mix", "value": 0.15}])),
        "histogram": histogram([grade, (0.2, 0.3, 0.4), (0.8, 0.7, 0.6)]),
        "kind": "film.cut",
        "mix": mix,
        "parade": rgb_parade([grade, (0.2, 0.25, 0.3), (0.7, 0.6, 0.5)]),
        "playhead": playhead,
        "playhead_cache": cache,
        "cache_hit": bool(cache.get("hash")),
        "razored": razored,
        "shots": shots,
        "tracks": max((s["track"] for s in shots), default=1),
        "transitions": transitions,
        "vectorscope": vectorscope(grade),
        "waveform": waveform([grade, (0.2, 0.3, 0.4)]),
        "dag": list(grade_dag(grade, [{"id": "cdl", "op": "cdl", "slope": 1.0}, {"id": "lut", "op": "lut", "input": "cdl", "table": [[0, 0], [0.5, 0.48], [1, 1]]}, {"id": "mix", "op": "mix", "input": "lut", "value": 0.2}])),
        "lut": list(lut_1d(grade, [(0.0, 0.0), (0.5, 0.48), (1.0, 1.0)])),
        "lutrgb": list(lut_rgb(grade)),
        "wipe": list(stills_wipe(grade, (0.2, 0.2, 0.2), 0.25)),
        "aces": list(aces_curve(grade)),
        "split": list(split_screen(grade, (0.1, 0.1, 0.1))),
        "cache": grade_cache(grade, [{"op": "cdl", "slope": 1.0}]),
        "false": list(false_color(grade)),
        "logosc": log_osc([grade, (0.2, 0.3, 0.4)]),
        "stills": grade_stills(grade, [{"id": "ref", "gain": 1.0}]),
        "rec709": list(rec709_encode(grade)),
        "roll": list(highlight_roll(grade)),
        "polar": vectorscope_polar(grade),
    }


def export_cut(desc: Desc) -> dict[str, Any]:
    """Assemble + EDL-like JSON. Local export, not a NLE product."""
    cut = assemble_film(desc)
    edl = []
    for i, shot in enumerate(cut["shots"], start=1):
        edl.append(
            {
                "clip": shot["clip"],
                "dst_in": shot["in"],
                "dst_out": shot["out"],
                "index": i,
                "track": shot["track"],
            }
        )
    for clip in cut["audio"]:
        edl.append(
            {
                "clip": clip["clip"],
                "dst_in": clip["in"],
                "kind": "audio",
                "offset": clip["offset"],
            }
        )
    return {"duration": cut["duration"], "edl": edl, "kind": "film.edl"}


def razor_shot(shots: list[dict[str, Any]], at: float) -> list[dict[str, Any]]:
    """Split the shot covering ``at`` into two clips (NLE razor)."""
    out: list[dict[str, Any]] = []
    for shot in shots:
        start = float(shot.get("in") or shot.get("at") or 0.0)
        dur = float(shot.get("duration") or 1.0)
        end = float(shot.get("out") or (start + dur))
        if start < at < end:
            left = dict(shot)
            left["out"] = at
            left["duration"] = at - start
            right = dict(shot)
            right["in"] = at
            right["at"] = at
            right["duration"] = end - at
            right["clip"] = str(shot.get("clip") or "shot") + "-b"
            out.extend([left, right])
        else:
            out.append(dict(shot))
    return out


def brep_solid(desc: Desc) -> dict[str, Any]:
    fields = _fields(desc)
    w = max(_num(fields, "width", 1.0), 0.01)
    h = max(_num(fields, "height", 1.0), 0.01)
    d = max(_num(fields, "depth", 1.0), 0.01)
    vertices = [
        (0, 0, 0),
        (w, 0, 0),
        (w, h, 0),
        (0, h, 0),
        (0, 0, d),
        (w, 0, d),
        (w, h, d),
        (0, h, d),
    ]
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5)]
    return {
        "depth": d,
        "edges": edges,
        "faces": faces,
        "height": h,
        "kind": "cad.brep",
        "vertices": vertices,
        "volume": w * h * d,
        "width": w,
        "bbox": (w, h, d),
        "area": 2 * (w * h + w * d + h * d),
    }


def settle_charge(desc: Desc, *, op: str = "capture") -> dict[str, Any]:
    fields = _fields(desc)
    amount = round(_num(fields, "amount", 0.0), 2)
    currency = _text(fields, "currency") or "usd"
    status = {"authorize": "authorized", "capture": "captured", "refund": "refunded"}.get(str(op), "captured")
    return {
        "amount": amount,
        "currency": currency,
        "kind": "commerce.settle",
        "op": status,
        "ref": _text(fields, "ref") or "local",
    }


def federate_messages(left: list[str], right: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in list(left or []) + list(right or []):
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def federate_channel(desc: Desc) -> dict[str, Any]:
    fields = _fields(desc)
    local = []
    for item in _items(fields, "messages"):
        if isinstance(item, AtomDesc) and item.has_value:
            local.append(str(item.value))
    remote = []
    for item in _items(fields, "remote"):
        if isinstance(item, AtomDesc) and item.has_value:
            remote.append(str(item.value))
    return {
        "kind": "social.federate",
        "messages": federate_messages(local, remote),
        "name": _text(fields, "name") or "channel",
    }


def weights_path(data_root: Path, name: str = DEFAULT_MODEL) -> Path:
    return resolve_model_path(data_root, name)


def complete_weights(prompt: str, *, data_root: Path, name: str = DEFAULT_MODEL) -> str:
    return infer_local(prompt, data_root=data_root, name=name or DEFAULT_MODEL, max_tokens=24, temperature=0.7)


def tokenize_local(text: str, *, limit: int = 2048) -> list[str]:
    parts = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", str(text or ""))
    return parts[: max(1, int(limit))]


def complete_session(
    *,
    prompt: str = "",
    messages: list[dict[str, Any]] | None = None,
    data_root: Path,
    name: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 256,
    system: str = "",
    context: int = 2048,
) -> dict[str, Any]:
    """Local completion from on-disk weights. Not a hosted LLM product."""
    lines: list[str] = []
    if system:
        lines.append(f"system: {system}")
    for row in messages or []:
        if not isinstance(row, dict):
            continue
        lines.append(f"{row.get('role') or 'user'}: {row.get('content') or ''}")
    if prompt:
        lines.append(f"user: {prompt}")
    window = tokenize_local("\n".join(lines), limit=max(32, min(8192, int(context))))
    raw = infer_local(
        " ".join(window),
        data_root=data_root,
        name=name or DEFAULT_MODEL,
        max_tokens=max(1, int(max_tokens)),
        temperature=float(temperature),
    )
    words = str(raw).split()[: max(1, int(max_tokens))]
    return {
        "context": len(window),
        "hosted": False,
        "kind": "ai",
        "local": True,
        "max_tokens": max(1, int(max_tokens)),
        "model": name or DEFAULT_MODEL,
        "output": " ".join(words),
        "temperature": float(temperature),
        "tokens": len(window),
    }


def complete_session_stream(
    *,
    prompt: str = "",
    messages: list[dict[str, Any]] | None = None,
    data_root: Path,
    name: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 256,
    system: str = "",
    context: int = 2048,
):
    session = complete_session(
        prompt=prompt,
        messages=messages,
        data_root=data_root,
        name=name,
        temperature=temperature,
        max_tokens=max_tokens,
        system=system,
        context=context,
    )
    pieces = str(session.get("output") or "").split()
    acc = []
    for part in pieces or infer_chunks(
        prompt,
        data_root=data_root,
        name=name or DEFAULT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
    ):
        acc.append(part)
        yield {
            "delta": part,
            "hosted": False,
            "local": True,
            "model": session["model"],
            "output": " ".join(acc),
        }


def identity4() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def mat_mul4(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    out = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            out[i][j] = sum(a[i][k] * b[k][j] for k in range(4))
    return out


def trs_matrix(
    px: float = 0.0,
    py: float = 0.0,
    pz: float = 0.0,
    rx: float = 0.0,
    ry: float = 0.0,
    rz: float = 0.0,
    sx: float = 1.0,
    sy: float = 1.0,
    sz: float = 1.0,
) -> list[list[float]]:
    """TRS 4x4. Scene graph structure, not a Unity runtime."""
    ax, ay, az = math.radians(rx), math.radians(ry), math.radians(rz)
    cx, sx_ = math.cos(ax), math.sin(ax)
    cy, sy_ = math.cos(ay), math.sin(ay)
    cz, sz_ = math.cos(az), math.sin(az)
    r00 = cy * cz
    r01 = cz * sx_ * sy_ - cx * sz_
    r02 = cx * cz * sy_ + sx_ * sz_
    r10 = cy * sz_
    r11 = cx * cz + sx_ * sy_ * sz_
    r12 = cx * sy_ * sz_ - cz * sx_
    r20 = -sy_
    r21 = cy * sx_
    r22 = cx * cy
    return [
        [r00 * sx, r01 * sy, r02 * sz, px],
        [r10 * sx, r11 * sy, r12 * sz, py],
        [r20 * sx, r21 * sy, r22 * sz, pz],
        [0.0, 0.0, 0.0, 1.0],
    ]


def mat_point(matrix: list[list[float]], x: float, y: float, z: float) -> tuple[float, float, float]:
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def camera_frustum(cam: dict, *, aspect: float = 16.0 / 9.0) -> dict[str, Any]:
    fov = max(10.0, min(170.0, float(cam.get("fov") or 60.0)))
    near = max(0.01, float(cam.get("near") or 0.1))
    far = max(near + 0.01, float(cam.get("far") or 100.0))
    f = 1.0 / math.tan(math.radians(fov) / 2.0)
    proj = [
        [f / aspect, 0.0, 0.0, 0.0],
        [0.0, f, 0.0, 0.0],
        [0.0, 0.0, (far + near) / (near - far), (2 * far * near) / (near - far)],
        [0.0, 0.0, -1.0, 0.0],
    ]
    return {
        "aspect": aspect,
        "far": far,
        "fov": fov,
        "matrix": proj,
        "near": near,
        "projection": str(cam.get("projection") or "perspective"),
        "x": float(cam.get("x") or 0.0),
        "y": float(cam.get("y") or 0.0),
        "z": float(cam.get("z") or 8.0),
    }


def light_at(light: dict, point: tuple[float, float, float]) -> float:
    kind = str(light.get("type") or "directional")
    intensity = max(0.0, float(light.get("intensity") or 1.0))
    lx, ly, lz = float(light.get("x") or 0.0), float(light.get("y") or 4.0), float(light.get("z") or 0.0)
    if kind == "directional":
        return intensity
    dx, dy, dz = point[0] - lx, point[1] - ly, point[2] - lz
    dist2 = dx * dx + dy * dy + dz * dz + 1e-4
    fall = intensity / dist2
    if kind == "spot":
        return fall * 0.5
    return fall


def _trs_from_fields(fields: dict) -> list[list[float]]:
    nested = fields.get("transform")
    src = _fields(nested) if isinstance(nested, StructDesc) else fields
    return trs_matrix(
        _num(src, "px", _num(fields, "x", 0.0)),
        _num(src, "py", _num(fields, "y", 0.0)),
        _num(src, "pz", _num(fields, "z", 0.0)),
        _num(src, "rx", 0.0),
        _num(src, "ry", 0.0),
        _num(src, "rz", 0.0),
        _num(src, "sx", 1.0),
        _num(src, "sy", 1.0),
        _num(src, "sz", 1.0),
    )


def scene_compile(desc: Desc) -> dict[str, Any]:
    fields = _fields(desc)
    root = _trs_from_fields(fields)
    cam_node = fields.get("camera")
    cam = _fields(cam_node) if isinstance(cam_node, StructDesc) else {}
    light_node = fields.get("light")
    light = _fields(light_node) if isinstance(light_node, StructDesc) else {}
    light_row = {
        "color": _text(light, "color") or "#fff4d6",
        "intensity": _num(light, "intensity", 1.0),
        "type": _text(light, "type") or "directional",
        "x": _num(light, "x", 2.0),
        "y": _num(light, "y", 4.0),
        "z": _num(light, "z", 1.0),
    }
    cam_dict = {
        "far": _num(cam, "far", 100.0),
        "fov": _num(cam, "fov", 60.0),
        "near": _num(cam, "near", 0.1),
        "projection": _text(cam, "projection") or "perspective",
        "x": _num(cam, "x", 0.0),
        "y": _num(cam, "y", 0.0),
        "z": _num(cam, "z", 8.0),
    }
    extra_lights = []
    for item in _items(fields, "lights"):
        row = _fields(item) if isinstance(item, StructDesc) else {}
        extra_lights.append(
            {
                "color": _text(row, "color") or "#ffffff",
                "intensity": _num(row, "intensity", 1.0),
                "type": _text(row, "type") or "point",
                "x": _num(row, "x", 0.0),
                "y": _num(row, "y", 2.0),
                "z": _num(row, "z", 0.0),
            }
        )
    lights = [light_row, *extra_lights]
    hierarchy = []
    origin = mat_point(root, 0.0, 0.0, 0.0)
    objects = _items(fields, "objects")
    if not objects:
        hierarchy.append(
            {
                "bind": "",
                "collider": "box",
                "illum": light_at(light_row, origin),
                "layer": _text(fields, "layer") or "Default",
                "mesh": _text(fields, "mesh") or "cube",
                "name": _text(fields, "title") or "Root",
                "parent": "",
                "static": _bool(fields, "static", False),
                "tag": _text(fields, "tag") or "Untagged",
                "weights": 1.0,
                "world": origin,
                "world_matrix": root,
            }
        )
    by_id: dict[str, list[list[float]]] = {"": root}
    for i, item in enumerate(objects):
        row = _fields(item) if isinstance(item, StructDesc) else {}
        parent = _text(row, "parent")
        local = _trs_from_fields(row)
        world_m = mat_mul4(by_id.get(parent, root), local)
        ident = _text(row, "id") or _text(row, "name") or f"obj-{i}"
        by_id[ident] = world_m
        pos = mat_point(world_m, 0.0, 0.0, 0.0)
        hierarchy.append(
            {
                "bind": _text(row, "bind"),
                "collider": _text(row, "collider") or "box",
                "illum": sum(light_at(src, pos) for src in lights),
                "layer": _text(row, "layer") or _text(fields, "layer") or "Default",
                "mesh": _text(row, "mesh") or _text(fields, "mesh") or "cube",
                "name": ident,
                "parent": parent,
                "static": _bool(row, "static", False),
                "tag": _text(row, "tag") or "Untagged",
                "weights": _num(row, "weight", 1.0),
                "world": pos,
                "world_matrix": world_m,
            }
        )
    cameras = _items(fields, "cameras")
    cam_rows = [camera_frustum(cam_dict)]
    for item in cameras:
        row = _fields(item) if isinstance(item, StructDesc) else {}
        cam_rows.append(
            camera_frustum(
                {
                    "far": _num(row, "far", 100.0),
                    "fov": _num(row, "fov", 60.0),
                    "near": _num(row, "near", 0.1),
                    "projection": _text(row, "projection") or "perspective",
                    "x": _num(row, "x", 0.0),
                    "y": _num(row, "y", 0.0),
                    "z": _num(row, "z", 8.0),
                }
            )
        )
    instances = []
    for item in _items(fields, "instances"):
        row = _fields(item) if isinstance(item, StructDesc) else {}
        local = _trs_from_fields(row)
        world_m = mat_mul4(root, local)
        instances.append(
            {
                "mesh": _text(row, "mesh") or _text(row, "proto") or _text(fields, "mesh") or "cube",
                "name": _text(row, "name") or _text(row, "id") or "instance",
                "world": mat_point(world_m, 0.0, 0.0, 0.0),
                "world_matrix": world_m,
            }
        )
    keys = []
    for item in _items(fields, "keys"):
        row = _fields(item) if isinstance(item, StructDesc) else {}
        keys.append(
            {
                "px": _num(row, "px", _num(row, "x", 0.0)),
                "py": _num(row, "py", _num(row, "y", 0.0)),
                "pz": _num(row, "pz", _num(row, "z", 0.0)),
                "t": _num(row, "t", 0.0),
            }
        )
    keys.sort(key=lambda row: row["t"])
    play_t = _num(fields, "time", _num(fields, "playhead", 0.0))
    played = {"px": 0.0, "py": 0.0, "pz": 0.0, "t": play_t}
    if keys:
        if play_t <= keys[0]["t"]:
            played = dict(keys[0])
            played["t"] = play_t
        elif play_t >= keys[-1]["t"]:
            played = dict(keys[-1])
            played["t"] = play_t
        else:
            for i in range(1, len(keys)):
                if keys[i]["t"] >= play_t:
                    a, b = keys[i - 1], keys[i]
                    span = max(1e-6, b["t"] - a["t"])
                    u = (play_t - a["t"]) / span
                    played = {
                        "px": a["px"] + (b["px"] - a["px"]) * u,
                        "py": a["py"] + (b["py"] - a["py"]) * u,
                        "pz": a["pz"] + (b["pz"] - a["pz"]) * u,
                        "t": play_t,
                    }
                    break
    return {
        "cameras": cam_rows,
        "fog": _num(fields, "fog", 0.0),
        "frustum": cam_rows[0],
        "graph": True,
        "hierarchy": hierarchy,
        "instances": instances,
        "keys": keys,
        "kind": "scene",
        "layers": sorted({str(row["layer"]) for row in hierarchy}),
        "lights": lights,
        "mesh": _text(fields, "mesh") or "cube",
        "play": played,
        "playing": _bool(fields, "playing", False) or bool(keys),
        "sky": _text(fields, "sky") or "procedural",
        "time": play_t,
        "unity": False,
    }


def kernel_spec(desc: Desc, *, data_root: Path | None = None) -> dict[str, Any]:
    fields = _fields(desc)
    kind = _text(fields, "kind")
    if kind == "physics.body":
        return step_physics(desc)
    if kind == "skeleton.rig":
        return step_skeleton(desc)
    if kind == "film.cut":
        out = assemble_film(desc)
        out["edl"] = export_cut(desc)["edl"]
        return out
    if kind == "cad.brep":
        return brep_solid(desc)
    if kind == "commerce.settle":
        return settle_charge(desc)
    if kind == "social.federate":
        return federate_channel(desc)
    if kind in {"ai", "llm.weights"}:
        model = _text(fields, "model") or DEFAULT_MODEL
        if data_root is None:
            return {
                "hosted": False,
                "kind": kind,
                "local": True,
                "model": model,
                "output": "",
                "tokens": len(tokenize_local(_text(fields, "prompt"))),
            }
        try:
            session = complete_session(
                prompt=_text(fields, "prompt"),
                data_root=Path(data_root),
                name=model,
                temperature=_num(fields, "temperature", 0.7),
                max_tokens=int(_num(fields, "max_tokens", 256)),
                system=_text(fields, "system"),
                context=int(_num(fields, "context", 2048)),
            )
        except WeightsError as exc:
            return {
                "error": str(exc),
                "hosted": False,
                "kind": kind,
                "local": True,
                "model": model,
                "output": "",
                "tokens": 0,
            }
        session["kind"] = kind
        return session
    if kind in {"circuit", "chip"}:
        nets = _items(fields, "nets")
        traces = []
        for i in range(max(1, len(nets))):
            row = _fields(nets[i]) if i < len(nets) and isinstance(nets[i], StructDesc) else {}
            trace = manhattan_route(0, float(i * 8), 80, float(i * 8 + 4), layer=int(_num(row, "layer", i % 2)))
            trace["net"] = _text(row, "name") or str(i)
            trace["width"] = _num(row, "width", 0.2)
            traces.append(trace)
        vias = []
        for item in _items(fields, "vias"):
            row = _fields(item) if isinstance(item, StructDesc) else {}
            vias.append(
                {
                    "drill": _num(row, "drill", 0.3),
                    "from": int(_num(row, "from", 0)),
                    "net": _text(row, "net") or "n1",
                    "size": _num(row, "size", 0.6),
                    "to": int(_num(row, "to", 1)),
                    "x": _num(row, "x", 0),
                    "y": _num(row, "y", 0),
                }
            )
        card = factory_deck(_text(fields, "deck") or "4L-FR4") if _text(fields, "deck") or _bool(fields, "factory", False) else process_card(
            {
                "clearance": _num(fields, "clearance", 4.0),
                "min_drill": _num(fields, "min_drill", 0.3),
                "min_width": _num(fields, "min_width", 0.0),
            }
        )
        pack = tapeout_pack(traces, vias=vias, card=card)
        return {
            "apertures": pack["apertures"],
            "card": pack["card"],
            "drc": pack["issues"],
            "gerber": pack["gerber"],
            "impedance": pack["impedance"],
            "keepout": pack["keepout"],
            "kind": kind,
            "netlist": pack["netlist"],
            "plated": pack["plated"],
            "stencil": pack["stencil"],
            "tapeout": pack,
            "traces": traces,
            "vias": vias,
        }
    if kind in {"print3d.job", "cnc.job"}:
        feed = _num(fields, "feed", 200)
        layer = _num(fields, "layer", 0.2)
        infill = _num(fields, "infill", 0.2)
        return {
            "gcode": f"; {kind}\nG21\nG90\nF{feed:.1f}\nG1 Z{layer:.3f}\nM2\n",
            "hatch": max(1, int(10 * infill)),
            "infill": infill,
            "kind": kind,
            "rpm": int(_num(fields, "rpm", 8000)),
        }
    if kind == "quantum":
        qubits = max(1, int(_num(fields, "qubit", 2)))
        amps = [1.0] + [0.0] * (2 ** qubits - 1)
        return {
            "amps": amps,
            "bloch": {"theta": math.acos(max(-1.0, min(1.0, amps[0]))), "z": amps[0]},
            "kind": kind,
            "qubits": qubits,
        }
    if kind == "spreadsheet":
        rows = _items(fields, "rows")
        total = 0.0
        for item in rows:
            row = _fields(item) if isinstance(item, StructDesc) else {}
            total += _num(row, "value", 0.0)
        return {"cols": int(_num(fields, "cols", 2)), "kind": kind, "rows": len(rows), "sum": total}
    if kind == "animation":
        duration = _num(fields, "duration", 1.0)
        fps = int(_num(fields, "fps", 24))
        return {
            "duration": duration,
            "fps": fps,
            "frames": max(1, int(round(duration * fps))),
            "keys": len(_items(fields, "keys")),
            "kind": kind,
        }
    if kind == "shader":
        src = _text(fields, "src") or "void main(){}"
        return {
            "blend": _text(fields, "blend") or "opaque",
            "kind": kind,
            "log": hashlib.sha256(src.encode("utf-8")).hexdigest()[:12],
            "precision": _text(fields, "precision") or "mediump",
        }
    if kind == "model3d":
        return {"kind": kind, "lod": _text(fields, "lod") or "high", "mesh": _text(fields, "mesh") or "body", "tris": int(_num(fields, "tris", 12))}
    if kind == "terrain":
        return {"kind": kind, "noise": _num(fields, "noise", 0.4), "seed": int(_num(fields, "seed", 1))}
    if kind == "particle":
        return {"count": int(_num(fields, "count", 32)), "kind": kind, "life": _num(fields, "life", 1.0)}
    if kind == "material":
        return {"kind": kind, "metal": _num(fields, "metal", 0.0), "rough": _num(fields, "rough", 0.5)}
    if kind == "map":
        zoom = int(_num(fields, "zoom", 3))
        return {"kind": kind, "lat": _num(fields, "lat", 0.0), "lng": _num(fields, "lng", 0.0), "tiles": 2 ** max(0, zoom), "zoom": zoom}
    if kind == "vr.space":
        return {"ipd": _num(fields, "ipd", 63), "kind": kind, "rig": _text(fields, "rig") or "room", "stereo": True}
    if kind == "robotics.cell":
        joints = max(2, int(_num(fields, "joints", 4)))
        return {
            "kind": kind,
            "program": [{"joint": i, "angle": 0.0} for i in range(joints)],
            "tcp": {"x": 0.0, "y": 0.0, "z": float(joints)},
        }
    if kind == "chain.ledger":
        blocks = max(1, int(_num(fields, "blocks", 3)))
        hashes = [f"loc{i:04d}" for i in range(blocks)]
        return {
            "blocks": [{"hash": h, "i": i} for i, h in enumerate(hashes)],
            "kind": kind,
            "local": True,
            "merkle": hashlib.sha256("".join(hashes).encode("utf-8")).hexdigest()[:16],
        }
    if kind in {"audio", "video"}:
        return {
            "channels": int(_num(fields, "channels", 2)),
            "duration": _num(fields, "duration", 1.0),
            "kind": kind,
            "rate": int(_num(fields, "rate", 48000 if kind == "audio" else 24)),
            "sample": _text(fields, "sample") or _text(fields, "clip") or "",
        }
    if kind == "text":
        body = _text(fields, "body")
        width = max(8, int(_num(fields, "width", 80)))
        return {"chars": len(body), "kind": kind, "lines": body.count("\n") + (1 if body else 0), "wrap": width}
    if kind == "vector":
        path = _text(fields, "path") or "M0 0 L1 1"
        return {"closed": _bool(fields, "closed", False), "commands": max(1, path.count(" ") // 2 + 1), "kind": kind, "path": path}
    if kind == "bitmap":
        w = int(_num(fields, "w", 64))
        h = int(_num(fields, "h", 64))
        return {"h": h, "kind": kind, "pixels": w * h, "w": w}
    if kind == "level":
        return {"kind": kind, "rooms": max(1, int(_num(fields, "rooms", 1))), "spawn": _text(fields, "spawn") or "start", "exits": len(_items(fields, "exits"))}
    if kind == "logic":
        return {"kind": kind, "states": max(1, int(_num(fields, "states", 2))), "transitions": len(_items(fields, "transitions"))}
    if kind == "font":
        return {"atlas": int(_num(fields, "size", 12) * 16), "glyphs": max(1, int(_num(fields, "glyphs", 26))), "kind": kind, "size": _num(fields, "size", 12)}
    if kind == "document":
        return {"blocks": len(_items(fields, "blocks")), "kind": kind, "pages": max(1, int(_num(fields, "pages", 1)))}
    if kind == "node":
        return {"kind": kind, "nodes": len(_items(fields, "nodes")), "wires": len(_items(fields, "wires"))}
    if kind == "ui":
        return {"kind": kind, "screens": max(1, int(_num(fields, "screens", 1))), "theme": _text(fields, "theme") or "dark"}
    if kind == "scene":
        graph = scene_compile(desc)
        if _bool(fields, "play", False):
            from meta.runtime.engine import play_frame

            frame = play_frame(
                desc,
                t=_num(fields, "t", 0.0),
                dt=_num(fields, "dt", 1.0 / 60.0),
                playing=True,
            )
            frame["hierarchy"] = graph.get("hierarchy")
            frame["instances"] = graph.get("instances")
            return frame
        return graph
    if kind == "data":
        return {"kind": kind, "tables": len(_items(fields, "tables")), "visual": True}
    return {"kind": kind, "ok": True}


def kernel_json(desc: Desc, *, data_root: Path | None = None) -> str:
    return json.dumps(kernel_spec(desc, data_root=data_root), ensure_ascii=False, sort_keys=True)
