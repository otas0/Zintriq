"""Compile a description or simulated machine into a host-independent artifact."""

from __future__ import annotations

import json
from typing import Iterable, Union

from meta.boundary import (
    BOUNDARY_KIND,
    META_DESKTOP_ID,
    META_SPACE_ID,
    SOFTWARE_PAGE_ID,
    WEB_BUILD_TARGET,
    get as get_boundary,
    install_from_desc,
)
from meta.boundary.errors import BoundaryError
from meta.description import Desc, from_json, to_json, validate_desc
from meta.description.composite import StructDesc
from meta.instantiation.artifact import (
    KNOWN_TARGETS,
    TARGET_CANVAS,
    TARGET_DESC,
    TARGET_DESKTOP_HOST,
    TARGET_DEVICE,
    TARGET_OS_HOST,
    TARGET_UIR,
    TARGET_VISUAL,
    TARGET_WEB_BUILD,
    Artifact,
    checksum_payload,
    public_url_for_slug,
    validate_slug,
)
from meta.instantiation.errors import InstantiationError
from meta.instantiation.system import (
    SYSTEM_KIND,
    _MAX_DEPTH,
    child_build_slug,
    install_all_boundaries,
    system_parts,
)
from meta.simulation import StateMachine, machine_from_desc, machine_to_desc, step
from meta.simulation.errors import SimulationError

Source = Union[Desc, StateMachine]


def apply_events(machine: StateMachine, events: Iterable[str]) -> StateMachine:
    current = machine
    for event in events:
        current = step(current, event)
    return current


def as_desc(source: Source) -> Desc:
    if isinstance(source, StateMachine):
        return machine_to_desc(source)
    validate_desc(source)
    return source


def instantiate(
    source: Source,
    *,
    target: str | None = None,
    boundary_id: str | None = None,
    slug: str | None = None,
    events: Iterable[str] | None = None,
    _depth: int = 0,
) -> Artifact:
    """Compile ``source`` (optionally after simulation events) to ``target``.

    A ``meta.boundary`` description is itself instantiable: it is registered,
    then compiled onto that boundary's instantiation target. A ``meta.system``
    description instantiates each part through this same path. Default compile
    is ``web_build``. Pass ``target=desktop_host`` to compile the system onto
    the existing Electron + local Flask host (not Unity).
    """
    desc = _advance(source, events)
    resolved_target, resolved_boundary = _resolve_for_desc(desc, target, boundary_id)
    if resolved_target == TARGET_DESC:
        payload = to_json(desc)
        return _artifact(
            TARGET_DESC,
            resolved_boundary,
            "application/json",
            payload,
            slug=slug,
        )
    if resolved_target == TARGET_WEB_BUILD:
        if _kind_name(desc) == SYSTEM_KIND:
            return _web_build_system(desc, slug, resolved_boundary, depth=_depth)
        return _web_build(desc, slug, resolved_boundary)
    if resolved_target == TARGET_UIR:
        from meta.uir import from_desc, to_code

        payload = to_code(from_desc(desc), language="json")
        return _artifact(TARGET_UIR, resolved_boundary, "application/json", payload, slug=slug)
    if resolved_target == TARGET_VISUAL:
        from meta.uir import desc_to_visual

        payload = json.dumps(desc_to_visual(desc), ensure_ascii=False, sort_keys=True)
        return _artifact(TARGET_VISUAL, resolved_boundary, "application/json", payload, slug=slug)
    if resolved_target == TARGET_DEVICE:
        from meta.runtime.hardware import device_artifact_body

        payload = json.dumps(device_artifact_body(desc, slug), ensure_ascii=False, sort_keys=True)
        return _artifact(TARGET_DEVICE, resolved_boundary, "application/json", payload, slug=slug)
    if resolved_target == TARGET_OS_HOST:
        from meta.runtime.os_surface import os_artifact_body

        payload = json.dumps(os_artifact_body(desc, slug), ensure_ascii=False, sort_keys=True)
        return _artifact(TARGET_OS_HOST, resolved_boundary, "application/json", payload, slug=slug)
    if resolved_target == TARGET_CANVAS:
        from meta.runtime.canvas import canvas_from_desc

        body = {
            "canvas": canvas_from_desc(desc),
            "description": json.loads(to_json(desc)),
        }
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
        return _artifact(TARGET_CANVAS, resolved_boundary, "application/json", payload, slug=slug)
    if resolved_target == TARGET_DESKTOP_HOST:
        if _kind_name(desc) == SYSTEM_KIND:
            return _desktop_host_system(desc, slug, resolved_boundary, depth=_depth)
        return _desktop_host(desc, slug, resolved_boundary)
    raise InstantiationError(f"unsupported target: {resolved_target!r}")


def _advance(source: Source, events: Iterable[str] | None) -> Desc:
    desc = as_desc(source)
    if not events:
        return desc
    try:
        machine = source if isinstance(source, StateMachine) else machine_from_desc(desc)
        machine = apply_events(machine, events)
    except SimulationError as exc:
        raise InstantiationError(str(exc)) from exc
    return machine_to_desc(machine)


def _kind_name(desc: Desc) -> str:
    if not isinstance(desc, StructDesc):
        return ""
    fields = {name: child for name, child in desc.fields}
    kind = fields.get("kind")
    from meta.description.types import AtomDesc

    if isinstance(kind, AtomDesc) and kind.has_value and isinstance(kind.value, str):
        return kind.value
    return ""


def _resolve_for_desc(
    desc: Desc,
    target: str | None,
    boundary_id: str | None,
) -> tuple[str, str]:
    if _kind_name(desc) == BOUNDARY_KIND:
        try:
            installed = install_from_desc(desc)
        except BoundaryError as exc:
            raise InstantiationError(str(exc)) from exc
        if not boundary_id:
            kind = str(target or "").strip() or installed.instantiation_target
            if kind not in KNOWN_TARGETS:
                raise InstantiationError(f"unsupported target: {kind!r}")
            return kind, installed.id
    try:
        install_all_boundaries(desc)
    except InstantiationError:
        raise
    except BoundaryError as exc:
        raise InstantiationError(str(exc)) from exc
    if not str(target or "").strip() and not str(boundary_id or "").strip():
        inferred_target, inferred_boundary = _infer_bound(desc)
        return _resolve_target(inferred_target, inferred_boundary)
    return _resolve_target(target, boundary_id)


_PAGE_KIND = "software.page"
_SITE_KIND = "software.site"
_MACHINE_KIND = "state_machine"


def _infer_target(desc: Desc) -> str:
    return _infer_bound(desc)[0]


def _id_name(desc: Desc) -> str:
    if not isinstance(desc, StructDesc):
        return ""
    ident = {name: child for name, child in desc.fields}.get("id")
    from meta.description.types import AtomDesc

    if isinstance(ident, AtomDesc) and ident.has_value and isinstance(ident.value, str):
        return ident.value
    return ""


def _infer_bound(desc: Desc) -> tuple[str, str]:
    kind = _kind_name(desc)
    ident = _id_name(desc)
    if kind == SYSTEM_KIND and ident == META_SPACE_ID:
        return TARGET_WEB_BUILD, META_SPACE_ID
    if kind == SYSTEM_KIND and ident == META_DESKTOP_ID:
        return TARGET_DESKTOP_HOST, META_DESKTOP_ID
    if kind == BOUNDARY_KIND:
        from meta.boundary import boundary_from_desc

        try:
            bound = boundary_from_desc(desc)
        except BoundaryError as exc:
            raise InstantiationError(str(exc)) from exc
        return bound.instantiation_target, bound.id
    if kind:
        try:
            bound = get_boundary(kind)
            return bound.instantiation_target, bound.id
        except BoundaryError:
            pass
    if kind in {SYSTEM_KIND, _PAGE_KIND, _SITE_KIND, _MACHINE_KIND}:
        return TARGET_WEB_BUILD, SOFTWARE_PAGE_ID
    return TARGET_DESC, "meta.core"


def _resolve_target(target: str | None, boundary_id: str | None) -> tuple[str, str]:
    key = str(boundary_id or "").strip()
    if key and key != "meta.core":
        try:
            boundary = get_boundary(key)
        except BoundaryError as exc:
            raise InstantiationError(str(exc)) from exc
        kind = str(target or "").strip() or boundary.instantiation_target
        if kind != boundary.instantiation_target:
            raise InstantiationError(
                f"target {kind!r} does not match boundary {boundary.id!r} "
                f"({boundary.instantiation_target})"
            )
        return kind, boundary.id
    kind = str(target or "").strip()
    if not kind:
        raise InstantiationError("target or boundary_id required")
    if kind not in KNOWN_TARGETS:
        raise InstantiationError(f"unsupported target: {kind!r}")
    if kind == WEB_BUILD_TARGET:
        return kind, SOFTWARE_PAGE_ID
    if kind == TARGET_DESKTOP_HOST:
        return kind, META_DESKTOP_ID
    return kind, "meta.core"


def _web_build_system(
    desc: Desc,
    slug: str | None,
    boundary_id: str,
    *,
    depth: int = 0,
) -> Artifact:
    if depth > _MAX_DEPTH:
        raise InstantiationError("meta.system nesting too deep")
    get_boundary(boundary_id)
    clean = validate_slug(slug)
    built = []
    for key, title, child in system_parts(desc):
        child_slug = child_build_slug(clean, key)
        child_kind = _kind_name(child)
        extra = {"_depth": depth + 1} if child_kind == SYSTEM_KIND else {}
        part_target, part_bound = _infer_bound(child)
        part = instantiate(
            child,
            target=part_target,
            boundary_id=part_bound,
            slug=child_slug,
            **extra,
        )
        built.append({"artifact": part.to_data(), "key": key, "title": title})
    public_url = public_url_for_slug(clean)
    body = {
        "description": json.loads(to_json(desc)),
        "parts": built,
        "public_url": public_url,
        "slug": clean,
    }
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return Artifact(
        target=TARGET_WEB_BUILD,
        boundary_id=boundary_id,
        media_type="application/json",
        payload=payload,
        checksum=checksum_payload(payload),
        public_url=public_url,
        slug=clean,
    )


def _desktop_host_system(
    desc: Desc,
    slug: str | None,
    boundary_id: str,
    *,
    depth: int = 0,
) -> Artifact:
    if depth > _MAX_DEPTH:
        raise InstantiationError("meta.system nesting too deep")
    get_boundary(boundary_id)
    clean = validate_slug(slug)
    built = []
    for key, title, child in system_parts(desc):
        child_slug = child_build_slug(clean, key)
        child_kind = _kind_name(child)
        extra = {"_depth": depth + 1} if child_kind == SYSTEM_KIND else {}
        part_target, part_bound = _infer_bound(child)
        part = instantiate(
            child,
            target=part_target,
            boundary_id=part_bound,
            slug=child_slug,
            **extra,
        )
        built.append({"artifact": part.to_data(), "key": key, "title": title})
    from meta.runtime.desktop_host import STUDIO_PATH, desktop_artifact_body

    body = desktop_artifact_body(desc, clean, parts=built)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return Artifact(
        target=TARGET_DESKTOP_HOST,
        boundary_id=boundary_id,
        media_type="application/json",
        payload=payload,
        checksum=checksum_payload(payload),
        public_url=STUDIO_PATH,
        slug=clean,
    )


def _desktop_host(desc: Desc, slug: str | None, boundary_id: str) -> Artifact:
    get_boundary(boundary_id)
    clean = validate_slug(slug)
    from meta.runtime.desktop_host import STUDIO_PATH, desktop_artifact_body

    body = desktop_artifact_body(desc, clean)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return Artifact(
        target=TARGET_DESKTOP_HOST,
        boundary_id=boundary_id,
        media_type="application/json",
        payload=payload,
        checksum=checksum_payload(payload),
        public_url=STUDIO_PATH,
        slug=clean,
    )


def _web_build(desc: Desc, slug: str | None, boundary_id: str) -> Artifact:
    get_boundary(boundary_id)
    clean = validate_slug(slug)
    public_url = public_url_for_slug(clean)
    body = {
        "description": json.loads(to_json(desc)),
        "public_url": public_url,
        "slug": clean,
    }
    if isinstance(desc, StructDesc):
        fields = {name: child for name, child in desc.fields}
        kind = fields.get("kind")
        from meta.description.types import AtomDesc

        if (
            isinstance(kind, AtomDesc)
            and kind.has_value
            and kind.value == "state_machine"
        ):
            body["machine_state"] = machine_from_desc(desc).state
    from meta.runtime.kernels import kernel_spec

    body["compiled"] = kernel_spec(desc)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return Artifact(
        target=TARGET_WEB_BUILD,
        boundary_id=boundary_id,
        media_type="application/json",
        payload=payload,
        checksum=checksum_payload(payload),
        public_url=public_url,
        slug=clean,
    )


def _artifact(
    target: str,
    boundary_id: str,
    media_type: str,
    payload: str,
    *,
    slug: str | None = None,
) -> Artifact:
    clean = None
    public_url = None
    if slug is not None and str(slug).strip():
        clean = validate_slug(slug)
        public_url = public_url_for_slug(clean)
    return Artifact(
        target=target,
        boundary_id=boundary_id,
        media_type=media_type,
        payload=payload,
        checksum=checksum_payload(payload),
        public_url=public_url,
        slug=clean,
    )


def description_from_artifact(artifact: Artifact) -> Desc:
    """Recover the description carried by a compiled artifact."""
    if artifact.target in {TARGET_WEB_BUILD, TARGET_DEVICE, TARGET_OS_HOST, TARGET_CANVAS, TARGET_DESKTOP_HOST}:
        data = artifact.payload_object()
        if not isinstance(data, dict) or "description" not in data:
            raise InstantiationError(f"{artifact.target} artifact missing description")
        return from_json(json.dumps(data["description"]))
    if artifact.target in {TARGET_DESC, TARGET_UIR}:
        return from_json(artifact.payload)
    if artifact.target == TARGET_VISUAL:
        from meta.uir import visual_to_desc

        return visual_to_desc(artifact.payload_object())
    raise InstantiationError(f"cannot recover description from {artifact.target!r}")
