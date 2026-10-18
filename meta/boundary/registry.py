"""Boundaries are meta objects: describe, register, look up, instantiate.

The first registered surface is ``software.page`` — a software/page system
that instantiates to the host public path ``/build/<slug>``.
A boundary description (``kind=meta.boundary``) can itself be instantiated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from meta.boundary.errors import BoundaryError
from meta.description.composite import SequenceDesc, StructDesc, sequence, struct
from meta.description.types import AtomDesc, Desc, atom

SOFTWARE_PAGE_ID = "software.page"
HARDWARE_MODULE_ID = "hardware.module"
OS_SURFACE_ID = "os.surface"
META_SPACE_ID = "meta.space"
META_DESKTOP_ID = "meta.desktop"
WEB_BUILD_TARGET = "web_build"
BOUNDARY_KIND = "meta.boundary"
SPACE_SYSTEM_KIND = "meta.system"
_BOUNDARY_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}(?:\.[a-z][a-z0-9-]{0,31}){0,3}$")
_SURFACES = frozenset({"software", "hardware", "os", "meta"})
_TARGETS = frozenset({"desc", "uir", "visual", "web_build", "device", "os_host", "canvas", "desktop_host"})


@dataclass(frozen=True)
class Boundary:
    id: str
    name: str
    kind: str
    instantiation_target: str
    meta_level: int = 0

    def to_data(self) -> dict:
        return {
            "id": self.id,
            "instantiation_target": self.instantiation_target,
            "kind": self.kind,
            "meta_level": self.meta_level,
            "name": self.name,
        }


SOFTWARE_PAGE = Boundary(
    id=SOFTWARE_PAGE_ID,
    name="Software page",
    kind="software",
    instantiation_target=WEB_BUILD_TARGET,
    meta_level=0,
)
HARDWARE_MODULE = Boundary(
    id=HARDWARE_MODULE_ID,
    name="Hardware module",
    kind="hardware",
    instantiation_target="device",
    meta_level=0,
)
OS_SURFACE = Boundary(
    id=OS_SURFACE_ID,
    name="OS surface",
    kind="os",
    instantiation_target="os_host",
    meta_level=0,
)
META_SPACE = Boundary(
    id=META_SPACE_ID,
    name="Meta space",
    kind="meta",
    instantiation_target=WEB_BUILD_TARGET,
    meta_level=1,
)
META_DESKTOP = Boundary(
    id=META_DESKTOP_ID,
    name="Desktop host",
    kind="meta",
    instantiation_target="desktop_host",
    meta_level=1,
)
DOMAIN_BOUNDARIES = (
    Boundary(id="scene", name="Scene", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="level", name="Level", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="shader", name="Shader", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="particle", name="Particle", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="terrain", name="Terrain", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="node.graph", name="Node graph", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="cad.solid", name="CAD solid", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="model3d", name="Model 3D", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="material", name="Material", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="vector", name="Vector", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="map", name="Map", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="circuit", name="Circuit", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="chip", name="Chip", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="quantum", name="Quantum", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="animation", name="Animation", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="video", name="Video", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="audio", name="Audio", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="bitmap", name="Bitmap", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="font", name="Font", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="media.channel", name="Media channel", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="social.channel", name="Social channel", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="commerce.checkout", name="Checkout", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="data.table", name="Data table", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="spreadsheet", name="Spreadsheet", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="document", name="Document", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="text", name="Text", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="ai", name="AI session", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="physics.body", name="Physics body", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="skeleton.rig", name="Skeleton", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="film.cut", name="Film cut", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="cad.brep", name="B-rep solid", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="commerce.settle", name="Settlement", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="social.federate", name="Federated channel", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="llm.weights", name="Local weights", kind="software", instantiation_target=WEB_BUILD_TARGET),
    # Expandable builtins: user-describable surfaces that instantiate to local
    # web_build / device hosts — not Unity / EDA / public-chain runtimes we ship.
    Boundary(id="vr.space", name="VR space", kind="software", instantiation_target=WEB_BUILD_TARGET),
    Boundary(id="robotics.cell", name="Robotics cell", kind="hardware", instantiation_target="device"),
    Boundary(id="print3d.job", name="3D print job", kind="hardware", instantiation_target="device"),
    Boundary(id="cnc.job", name="CNC job", kind="hardware", instantiation_target="device"),
    Boundary(id="chain.ledger", name="Chain ledger", kind="software", instantiation_target=WEB_BUILD_TARGET),
)

_REGISTRY: dict[str, Boundary] = {}
_BUILTINS_LOADED = False
_SPACE: StructDesc | None = None


def _ensure_builtins() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _REGISTRY[SOFTWARE_PAGE.id] = SOFTWARE_PAGE
    _REGISTRY[HARDWARE_MODULE.id] = HARDWARE_MODULE
    _REGISTRY[OS_SURFACE.id] = OS_SURFACE
    _REGISTRY[META_SPACE.id] = META_SPACE
    _REGISTRY[META_DESKTOP.id] = META_DESKTOP
    for bound in DOMAIN_BOUNDARIES:
        _REGISTRY[bound.id] = bound
    _BUILTINS_LOADED = True
    _touch_space()


def register(boundary: Boundary) -> Boundary:
    _ensure_builtins()
    if not isinstance(boundary, Boundary):
        raise BoundaryError("boundary must be a Boundary")
    if not boundary.id or not boundary.id.strip():
        raise BoundaryError("boundary id required")
    if boundary.id in _REGISTRY:
        raise BoundaryError(f"boundary already registered: {boundary.id!r}")
    if boundary.meta_level < 0:
        raise BoundaryError("meta_level must be >= 0")
    if not boundary.instantiation_target:
        raise BoundaryError("instantiation_target required")
    _REGISTRY[boundary.id] = boundary
    _touch_space()
    return boundary


def get(boundary_id: str) -> Boundary:
    _ensure_builtins()
    key = str(boundary_id or "").strip()
    found = _REGISTRY.get(key)
    if found is None:
        raise BoundaryError(f"unknown boundary: {key!r}")
    return found


def unused_boundary_id(prefix: str = "software.part") -> str:
    _ensure_builtins()
    base = str(prefix or "software.part").strip() or "software.part"
    n = 1
    while n < 1000:
        ident = base if n == 1 else f"{base}-{n}"
        try:
            validate_boundary_id(ident)
        except BoundaryError as exc:
            raise BoundaryError(str(exc)) from exc
        if ident not in _REGISTRY:
            return ident
        n += 1
    raise BoundaryError("no unused boundary id")


def list_boundaries() -> tuple[Boundary, ...]:
    _ensure_builtins()
    return tuple(sorted(_REGISTRY.values(), key=lambda item: item.id))


def validate_boundary_id(value: str) -> str:
    key = str(value or "").strip()
    if not _BOUNDARY_ID.fullmatch(key):
        raise BoundaryError("boundary id must be dotted lowercase tokens")
    return key


def boundary_to_desc(boundary: Boundary) -> StructDesc:
    """Boundary as a description — same form as any other meta object."""
    if not isinstance(boundary, Boundary):
        raise BoundaryError("boundary must be a Boundary")
    return struct(
        id=atom("string", value=boundary.id, has_value=True),
        kind=atom("string", value=BOUNDARY_KIND, has_value=True),
        meta_level=atom("int", value=int(boundary.meta_level), has_value=True),
        name=atom("string", value=boundary.name, has_value=True),
        surface=atom("string", value=boundary.kind, has_value=True),
        target=atom("string", value=boundary.instantiation_target, has_value=True),
    )


def boundary_from_desc(node: Desc) -> Boundary:
    if not isinstance(node, StructDesc):
        raise BoundaryError("boundary description must be a struct")
    fields = dict(node.fields)
    kind = _atom_string(fields, "kind")
    if kind != BOUNDARY_KIND:
        raise BoundaryError("description kind must be meta.boundary")
    ident = validate_boundary_id(_atom_string(fields, "id"))
    name = _atom_string(fields, "name") or ident
    surface = _atom_string(fields, "surface") or "software"
    if surface not in _SURFACES:
        raise BoundaryError("surface must be software, hardware, os, or meta")
    target = _atom_string(fields, "target")
    if target not in _TARGETS:
        raise BoundaryError("target must be desc, uir, visual, web_build, device, os_host, canvas, or desktop_host")
    level = _atom_int(fields, "meta_level")
    if level is None:
        level = 0
    if level < 0:
        raise BoundaryError("meta_level must be >= 0")
    return Boundary(
        id=ident,
        name=name,
        kind=surface,
        instantiation_target=target,
        meta_level=level,
    )


def install_from_desc(node: Desc) -> Boundary:
    """Register a described boundary. Same id with the same definition is a no-op."""
    boundary = boundary_from_desc(node)
    _ensure_builtins()
    existing = _REGISTRY.get(boundary.id)
    if existing is None:
        _REGISTRY[boundary.id] = boundary
        _touch_space()
        return boundary
    if existing != boundary:
        raise BoundaryError(f"boundary already registered: {boundary.id!r}")
    return existing


def space_desc() -> StructDesc:
    """The meta-system whose parts are the registered boundaries."""
    _ensure_builtins()
    global _SPACE
    if _SPACE is None:
        _SPACE = _build_space()
    return _SPACE


def space_boundary_ids() -> tuple[str, ...]:
    """Boundary ids that exist as parts of the meta-system (not meta.space itself)."""
    node = space_desc()
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        return ()
    ids = []
    for item in parts.items:
        if not isinstance(item, StructDesc):
            continue
        child = dict(item.fields).get("of")
        if child is None:
            continue
        try:
            ids.append(boundary_from_desc(child).id)
        except BoundaryError:
            continue
    return tuple(ids)


def _part_key(ident: str) -> str:
    return str(ident).replace(".", "-")


def _build_space() -> StructDesc:
    nodes = []
    for bound in sorted(
        (item for item in _REGISTRY.values() if item.id != META_SPACE_ID),
        key=lambda item: item.id,
    ):
        nodes.append(
            struct(
                key=atom("string", value=_part_key(bound.id), has_value=True),
                of=boundary_to_desc(bound),
                title=atom("string", value=bound.name, has_value=True),
            )
        )
    if not nodes:
        raise BoundaryError("meta space requires boundaries")
    return struct(
        id=atom("string", value=META_SPACE_ID, has_value=True),
        kind=atom("string", value=SPACE_SYSTEM_KIND, has_value=True),
        parts=sequence(*nodes),
        title=atom("string", value="Meta", has_value=True),
    )


def _touch_space() -> None:
    global _SPACE
    _SPACE = None


def _atom_string(fields: dict[str, Desc], name: str) -> str:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value and node.type_name == "string":
        return str(node.value or "")
    return ""


def _atom_int(fields: dict[str, Desc], name: str) -> int | None:
    node = fields.get(name)
    if not isinstance(node, AtomDesc) or not node.has_value or node.type_name != "int":
        return None
    if isinstance(node.value, bool) or not isinstance(node.value, int):
        return None
    return node.value


def reset_for_tests() -> None:
    """Drop non-builtin entries. Builtins stay registered."""
    global _BUILTINS_LOADED
    _REGISTRY.clear()
    _BUILTINS_LOADED = False
    _ensure_builtins()
