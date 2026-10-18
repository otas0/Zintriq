"""Composite meta-system: a description whose parts are other descriptions."""

from __future__ import annotations

from meta.boundary import BOUNDARY_KIND, install_from_desc
from meta.boundary.errors import BoundaryError
from meta.description.composite import MappingDesc, SequenceDesc, StructDesc, sequence, struct
from meta.description.types import AtomDesc, Desc, atom
from meta.instantiation.artifact import TARGET_WEB_BUILD, Artifact, validate_slug
from meta.instantiation.errors import InstantiationError

SYSTEM_KIND = "meta.system"
SITE_KIND = "software.site"
# Practical stack bound only. meta_level is unbounded; cycles are rejected.
_MAX_DEPTH = 256
_MAX_PARTS = 64


def software_system(
    *,
    title: str,
    parts: tuple[tuple[str, str, Desc], ...] | list[tuple[str, str, Desc]] = (),
) -> StructDesc:
    """System description: ordered parts, each a full description."""
    nodes = []
    seen: set[str] = set()
    for key, part_title, child in parts:
        slug = validate_slug(key)
        if slug in seen:
            raise InstantiationError("duplicate system part key")
        seen.add(slug)
        if not isinstance(child, (AtomDesc, StructDesc, SequenceDesc, MappingDesc)):
            raise InstantiationError("system part must be a description")
        label = str(part_title or slug).strip() or slug
        nodes.append(
            struct(
                key=atom("string", value=slug, has_value=True),
                of=child,
                title=atom("string", value=label, has_value=True),
            )
        )
    if not nodes:
        raise InstantiationError("meta.system requires at least one part")
    return struct(
        kind=atom("string", value=SYSTEM_KIND, has_value=True),
        parts=sequence(*nodes),
        title=atom("string", value=str(title), has_value=True),
    )


def system_parts(node: Desc) -> tuple[tuple[str, str, Desc], ...]:
    """(key, title, child-desc) in definition order."""
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        return ()
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        return ()
    rows = []
    seen: set[str] = set()
    for item in parts.items:
        if not isinstance(item, StructDesc):
            continue
        fields = dict(item.fields)
        key = _string_field(fields, "key")
        try:
            slug = validate_slug(key)
        except InstantiationError:
            continue
        if slug in seen:
            continue
        child = fields.get("of")
        if child is None:
            continue
        seen.add(slug)
        title = _string_field(fields, "title") or slug
        rows.append((slug, title, child))
    return tuple(rows)


def flatten_system_pages(
    node: Desc,
    *,
    prefix: str = "",
    depth: int = 0,
    _seen: frozenset[int] | None = None,
) -> tuple[tuple[str, str, Desc], ...]:
    """Flatten nested systems into (key, title, desc) pages under one /build slug."""
    if _kind_of(node) != SYSTEM_KIND:
        return ()
    seen = _seen or frozenset()
    mark = id(node)
    if mark in seen:
        raise InstantiationError("meta.system cycle")
    if depth > _MAX_DEPTH:
        raise InstantiationError("meta.system nesting too deep")
    nxt = seen | {mark}
    rows: list[tuple[str, str, Desc]] = []
    for key, title, child in system_parts(node):
        full = validate_slug(f"{prefix}-{key}" if prefix else key)
        kind = _kind_of(child)
        if kind == SITE_KIND:
            site_rows = prefixed_site_pages(full, child)
            if site_rows:
                rows.extend(site_rows)
            else:
                rows.append((full, title, child))
        else:
            rows.append((full, title, child))
            if kind == SYSTEM_KIND:
                rows.extend(flatten_system_pages(child, prefix=full, depth=depth + 1, _seen=nxt))
    if len(rows) > _MAX_PARTS:
        raise InstantiationError("too many system parts")
    return tuple(rows)


def prefixed_site_pages(prefix: str, node: Desc) -> tuple[tuple[str, str, Desc], ...]:
    """Map a software.site's pages onto system keys (home stays ``prefix``)."""
    rows = _site_page_rows(node)
    if not rows:
        return ()
    home = "home" if any(key == "home" for key, _title, _page in rows) else rows[0][0]
    out: list[tuple[str, str, Desc]] = []
    for key, title, page in rows:
        full = prefix if key == home else validate_slug(f"{prefix}-{key}")
        out.append((full, title, page))
    return tuple(out)


def _site_page_rows(node: Desc) -> tuple[tuple[str, str, Desc], ...]:
    if _kind_of(node) != SITE_KIND or not isinstance(node, StructDesc):
        return ()
    pages = dict(node.fields).get("pages")
    if not isinstance(pages, SequenceDesc):
        return ()
    rows: list[tuple[str, str, Desc]] = []
    seen: set[str] = set()
    for item in pages.items:
        if not isinstance(item, StructDesc):
            continue
        fields = dict(item.fields)
        key = _string_field(fields, "key")
        try:
            slug = validate_slug(key)
        except InstantiationError:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        title = _string_field(fields, "title") or slug
        rows.append((slug, title, item))
    return tuple(rows)


def resolve_system_part(node: Desc, page_key: str | None) -> tuple[str, str, Desc] | None:
    rows = flatten_system_pages(node)
    if not rows:
        return None
    wanted = str(page_key or "").strip()
    if not wanted:
        return rows[0]
    for key, title, child in rows:
        if key == wanted:
            return key, title, child
    return None


def child_build_slug(parent: str, key: str) -> str:
    root = validate_slug(parent)
    part = validate_slug(key)
    joined = f"{root}-{part}"
    if len(joined) <= 64:
        return joined
    return part


def system_built_parts(
    artifact: Artifact,
    *,
    prefix: str = "",
    depth: int = 0,
) -> tuple[tuple[str, str, Artifact], ...]:
    """Flatten instantiated system parts from a parent web_build payload."""
    if artifact.target != TARGET_WEB_BUILD:
        return ()
    try:
        data = artifact.payload_object()
    except InstantiationError:
        return ()
    if not isinstance(data, dict):
        return ()
    raw = data.get("parts")
    if not isinstance(raw, list):
        return ()
    if depth > _MAX_DEPTH:
        raise InstantiationError("meta.system nesting too deep")
    rows: list[tuple[str, str, Artifact]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        try:
            full = validate_slug(f"{prefix}-{key}" if prefix else key)
        except InstantiationError:
            continue
        try:
            child = Artifact.from_data(item.get("artifact") or {})
        except InstantiationError:
            continue
        title = str(item.get("title") or full)
        rows.append((full, title, child))
        if child.target == TARGET_WEB_BUILD:
            rows.extend(system_built_parts(child, prefix=full, depth=depth + 1))
    if len(rows) > _MAX_PARTS:
        raise InstantiationError("too many system parts")
    return tuple(rows)


def part_at_path(node: Desc, path: tuple[str, ...]) -> Desc:
    """Child description at an ordered list of system part keys."""
    current = node
    if not path:
        raise InstantiationError("system part path required")
    for key in path:
        wanted = validate_slug(key)
        found = None
        for slug, _title, child in system_parts(current):
            if slug == wanted:
                found = child
                break
        if found is None:
            raise InstantiationError("unknown system part")
        current = found
    return current


def replace_system_path(node: Desc, path: tuple[str, ...], child: Desc) -> StructDesc:
    """Replace the ``of`` description at ``path`` (nested systems allowed)."""
    if not path:
        raise InstantiationError("system part path required")
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("replace requires meta.system")
    key = validate_slug(path[0])
    rest = path[1:]
    replacement = child
    if rest:
        replacement = replace_system_path(part_at_path(node, (key,)), rest, child)
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        raise InstantiationError("meta.system requires parts")
    rebuilt = []
    found = False
    for item in parts.items:
        if not isinstance(item, StructDesc):
            rebuilt.append(item)
            continue
        fields = dict(item.fields)
        try:
            slug = validate_slug(_string_field(fields, "key"))
        except InstantiationError:
            rebuilt.append(item)
            continue
        if slug == key:
            fields["of"] = replacement
            found = True
            rebuilt.append(struct(**fields))
        else:
            rebuilt.append(item)
    if not found:
        raise InstantiationError("unknown system part")
    root = dict(node.fields)
    root["parts"] = sequence(*rebuilt)
    return struct(**root)


def locate_site_page(
    node: Desc,
    page_key: str | None,
    *,
    prefix: str = "",
    depth: int = 0,
    path: tuple[str, ...] = (),
) -> tuple[tuple[str, ...], str] | None:
    """Map a flattened system page key to ``(part path, local software.site page key)``."""
    if _kind_of(node) != SYSTEM_KIND:
        return None
    if depth > _MAX_DEPTH:
        raise InstantiationError("meta.system nesting too deep")
    wanted = str(page_key or "").strip()
    if not wanted:
        return None
    for key, _title, child in system_parts(node):
        full = validate_slug(f"{prefix}-{key}" if prefix else key)
        here = path + (key,)
        kind = _kind_of(child)
        if kind == SITE_KIND:
            for mapped, _title, page in prefixed_site_pages(full, child):
                if mapped != wanted or not isinstance(page, StructDesc):
                    continue
                local = _string_field(dict(page.fields), "key")
                try:
                    return here, validate_slug(local)
                except InstantiationError:
                    return None
        elif kind == SYSTEM_KIND:
            found = locate_site_page(
                child,
                wanted,
                prefix=full,
                depth=depth + 1,
                path=here,
            )
            if found is not None:
                return found
    return None


def flattened_page_key(path: tuple[str, ...], site: Desc, local_key: str) -> str:
    prefix = "-".join(path)
    wanted = validate_slug(local_key)
    for mapped, _title, page in prefixed_site_pages(prefix, site):
        if not isinstance(page, StructDesc):
            continue
        if _string_field(dict(page.fields), "key") == wanted:
            return mapped
    raise InstantiationError("unknown site page")


def part_home_key(path: tuple[str, ...], part_key: str) -> str:
    prefix = "-".join(path)
    slug = validate_slug(part_key)
    if prefix:
        return validate_slug(f"{prefix}-{slug}")
    return slug


def locate_owning_part(
    node: Desc,
    page_key: str | None,
    *,
    prefix: str = "",
    depth: int = 0,
    path: tuple[str, ...] = (),
) -> tuple[tuple[str, ...], str] | None:
    """System path + direct part key that owns a flattened page key."""
    if _kind_of(node) != SYSTEM_KIND:
        return None
    if depth > _MAX_DEPTH:
        raise InstantiationError("meta.system nesting too deep")
    wanted = str(page_key or "").strip()
    if not wanted:
        return None
    for key, _title, child in system_parts(node):
        full = validate_slug(f"{prefix}-{key}" if prefix else key)
        kind = _kind_of(child)
        if kind == SITE_KIND:
            for mapped, _title, _page in prefixed_site_pages(full, child):
                if mapped == wanted:
                    return path, key
        elif kind == SYSTEM_KIND:
            if full == wanted:
                return path, key
            found = locate_owning_part(
                child,
                wanted,
                prefix=full,
                depth=depth + 1,
                path=path + (key,),
            )
            if found is not None:
                return found
        elif full == wanted:
            return path, key
    return None


def _unused_part_key(existing: set[str]) -> str:
    if "part" not in existing:
        return "part"
    n = 2
    while n <= _MAX_PARTS + 1:
        candidate = f"part-{n}"
        if candidate not in existing:
            return candidate
        n += 1
    raise InstantiationError("too many system parts")


def child_for_part_kind(kind: str, *, title: str = "") -> Desc:
    """Default description for a new system part."""
    wanted = str(kind or "page").strip().lower() or "page"
    aliases = {
        "broadcast": "media.channel",
        "cad": "cad.solid",
        "channel": "social.channel",
        "checkout": "commerce.checkout",
        "game": "scene",
        "physics": "physics.body",
        "skeleton": "skeleton.rig",
        "film": "film.cut",
        "brep": "cad.brep",
        "settle": "commerce.settle",
        "federate": "social.federate",
        "weights": "llm.weights",
    }
    wanted = aliases.get(wanted, wanted)
    label = str(title or "").strip() or "Part"
    if wanted in {"page", "software.page"}:
        return struct(
            body=sequence(atom("string", value="New part.", has_value=True)),
            kind=atom("string", value="software.page", has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted in {"boundary", "meta.boundary"}:
        from meta.boundary import Boundary, WEB_BUILD_TARGET, boundary_to_desc, unused_boundary_id

        ident = unused_boundary_id()
        return boundary_to_desc(
            Boundary(
                id=ident,
                name=label,
                kind="software",
                instantiation_target=WEB_BUILD_TARGET,
                meta_level=0,
            )
        )
    if wanted in {"hardware", "hardware.module"}:
        from meta.boundary import HARDWARE_MODULE_ID

        return struct(
            act=atom("string", value="none", has_value=True),
            display=atom("string", value="none", has_value=True),
            kind=atom("string", value=HARDWARE_MODULE_ID, has_value=True),
            sense=atom("string", value="none", has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted in {"os", "os.surface"}:
        from meta.boundary import OS_SURFACE_ID

        return struct(
            kind=atom("string", value=OS_SURFACE_ID, has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    from meta.boundary import get as get_boundary
    from meta.boundary.errors import BoundaryError
    from meta.runtime.world import WORLD_KINDS, seed_desc

    try:
        bound = get_boundary(wanted)
    except BoundaryError:
        bound = None
    if bound is not None and bound.id in WORLD_KINDS:
        return seed_desc(bound.id, label)
    if wanted in WORLD_KINDS:
        return seed_desc(wanted, label)
    raise InstantiationError(f"unsupported part kind: {wanted!r}")


def add_system_part(
    node: Desc,
    *,
    key: str | None = None,
    title: str = "",
    child: Desc | None = None,
    part_kind: str | None = None,
) -> StructDesc:
    """Append one part to a meta.system. Default child is software.page."""
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("add_system_part requires meta.system")
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        raise InstantiationError("meta.system requires parts")
    existing = {item[0] for item in system_parts(node)}
    if len(existing) >= _MAX_PARTS:
        raise InstantiationError("too many system parts")
    wanted = str(key or "").strip()
    slug = validate_slug(wanted) if wanted else _unused_part_key(existing)
    if slug in existing:
        raise InstantiationError("duplicate system part key")
    label = str(title or "").strip() or slug.replace("-", " ").title()
    if child is None:
        child = child_for_part_kind(part_kind or "page", title=label)
    elif not isinstance(child, (AtomDesc, StructDesc, SequenceDesc, MappingDesc)):
        raise InstantiationError("system part must be a description")
    if _kind_of(child) == BOUNDARY_KIND:
        try:
            install_from_desc(child)
        except BoundaryError as exc:
            raise InstantiationError(str(exc)) from exc
    added = struct(
        key=atom("string", value=slug, has_value=True),
        of=child,
        title=atom("string", value=label, has_value=True),
    )
    fields = dict(node.fields)
    fields["parts"] = sequence(*parts.items, added)
    return struct(**fields)


def remove_system_part(node: Desc, key: str) -> StructDesc:
    """Drop one direct part; at least one part must remain."""
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("remove_system_part requires meta.system")
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        raise InstantiationError("meta.system requires parts")
    slug = validate_slug(str(key or "").strip())
    kept = []
    removed = False
    for item in parts.items:
        if isinstance(item, StructDesc) and _string_field(dict(item.fields), "key") == slug:
            removed = True
            continue
        kept.append(item)
    if not removed:
        raise InstantiationError("unknown system part")
    remaining = []
    for item in kept:
        if not isinstance(item, StructDesc):
            continue
        try:
            validate_slug(_string_field(dict(item.fields), "key"))
        except InstantiationError:
            continue
        remaining.append(item)
    if not remaining:
        raise InstantiationError("meta.system requires at least one part")
    fields = dict(node.fields)
    fields["parts"] = sequence(*kept)
    return struct(**fields)


_TITLE_MAX = 120


def _part_structs(node: StructDesc) -> list[StructDesc]:
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        return []
    rows = []
    for item in parts.items:
        if not isinstance(item, StructDesc):
            continue
        try:
            validate_slug(_string_field(dict(item.fields), "key"))
        except InstantiationError:
            continue
        rows.append(item)
    return rows


def _copy_part_key(base: str, existing: set[str]) -> str:
    n = 2
    while n <= _MAX_PARTS + 1:
        candidate = f"{base}-{n}"
        if candidate not in existing:
            return validate_slug(candidate)
        n += 1
    raise InstantiationError("too many system parts")


def move_system_part(node: Desc, key: str, *, delta: int) -> StructDesc:
    """Swap a direct part with its neighbor. delta is -1 or 1."""
    if delta not in (-1, 1):
        raise InstantiationError("delta must be -1 or 1")
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("move_system_part requires meta.system")
    slug = validate_slug(str(key or "").strip())
    items = _part_structs(node)
    keys = [_string_field(dict(item.fields), "key") for item in items]
    try:
        index = keys.index(slug)
    except ValueError as exc:
        raise InstantiationError("unknown system part") from exc
    other = index + delta
    if other < 0 or other >= len(keys):
        return node
    items[index], items[other] = items[other], items[index]
    fields = dict(node.fields)
    fields["parts"] = sequence(*items)
    return struct(**fields)


def duplicate_system_part(node: Desc, key: str) -> StructDesc:
    """Copy one direct part after the source, with a new key."""
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("duplicate_system_part requires meta.system")
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        raise InstantiationError("meta.system requires parts")
    slug = validate_slug(str(key or "").strip())
    existing = {item[0] for item in system_parts(node)}
    if slug not in existing:
        raise InstantiationError("unknown system part")
    if len(existing) >= _MAX_PARTS:
        raise InstantiationError("too many system parts")
    source = None
    label = slug
    for item in _part_structs(node):
        fields = dict(item.fields)
        if _string_field(fields, "key") == slug:
            source = item
            label = _string_field(fields, "title") or slug
            break
    if source is None:
        raise InstantiationError("unknown system part")
    new_key = _copy_part_key(slug, existing)
    copy_title = str(label or new_key).strip()
    if copy_title and not copy_title.lower().endswith(" copy"):
        copy_title = f"{copy_title} copy"
    if len(copy_title) > _TITLE_MAX:
        copy_title = copy_title[:_TITLE_MAX].rstrip()
    fields = dict(source.fields)
    fields["key"] = atom("string", value=new_key, has_value=True)
    fields["title"] = atom("string", value=copy_title or new_key, has_value=True)
    cloned = struct(**fields)
    rebuilt = []
    inserted = False
    for item in parts.items:
        rebuilt.append(item)
        if (
            not inserted
            and isinstance(item, StructDesc)
            and _string_field(dict(item.fields), "key") == slug
        ):
            rebuilt.append(cloned)
            inserted = True
    if not inserted:
        rebuilt.append(cloned)
    root = dict(node.fields)
    root["parts"] = sequence(*rebuilt)
    return struct(**root)


def set_part_title(node: Desc, key: str, title: str) -> StructDesc:
    """Replace the wrapper title of one direct system part."""
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("set_part_title requires meta.system")
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        raise InstantiationError("meta.system requires parts")
    slug = validate_slug(str(key or "").strip())
    label = str(title or "").strip()
    if not label:
        raise InstantiationError("title required")
    if len(label) > _TITLE_MAX:
        raise InstantiationError("title too long")
    rebuilt = []
    found = False
    for item in parts.items:
        if isinstance(item, StructDesc) and _string_field(dict(item.fields), "key") == slug:
            fields = dict(item.fields)
            fields["title"] = atom("string", value=label, has_value=True)
            rebuilt.append(struct(**fields))
            found = True
        else:
            rebuilt.append(item)
    if not found:
        raise InstantiationError("unknown system part")
    root = dict(node.fields)
    root["parts"] = sequence(*rebuilt)
    return struct(**root)


def set_system_title(node: Desc, title: str) -> StructDesc:
    """Replace the root title of a meta.system."""
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("set_system_title requires meta.system")
    label = str(title or "").strip()
    if not label:
        raise InstantiationError("title required")
    if len(label) > _TITLE_MAX:
        raise InstantiationError("title too long")
    fields = dict(node.fields)
    fields["title"] = atom("string", value=label, has_value=True)
    return struct(**fields)


def root_system_title(node: Desc) -> str | None:
    """Root title of a meta.system, or None."""
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        return None
    label = _string_field(dict(node.fields), "title")
    return label or None


def rename_system_part(node: Desc, key: str, new_key: str) -> StructDesc:
    """Rename a direct system part key."""
    if _kind_of(node) != SYSTEM_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("rename_system_part requires meta.system")
    parts = dict(node.fields).get("parts")
    if not isinstance(parts, SequenceDesc):
        raise InstantiationError("meta.system requires parts")
    old = validate_slug(str(key or "").strip())
    new = validate_slug(str(new_key or "").strip())
    if old == new:
        return node
    existing = {item[0] for item in system_parts(node)}
    if old not in existing:
        raise InstantiationError("unknown system part")
    if new in existing:
        raise InstantiationError("duplicate system part key")
    rebuilt = []
    found = False
    for item in parts.items:
        if isinstance(item, StructDesc) and _string_field(dict(item.fields), "key") == old:
            fields = dict(item.fields)
            fields["key"] = atom("string", value=new, has_value=True)
            rebuilt.append(struct(**fields))
            found = True
        else:
            rebuilt.append(item)
    if not found:
        raise InstantiationError("unknown system part")
    root = dict(node.fields)
    root["parts"] = sequence(*rebuilt)
    return struct(**root)


def apply_system_part_op(node: Desc, page_key: str | None, fn) -> tuple[Desc, str]:
    """Run ``fn(system, part_key) -> (system, part_key)`` on the owning system."""
    if _kind_of(node) != SYSTEM_KIND:
        raise InstantiationError("requires meta.system")
    wanted = str(page_key or "").strip()
    if not wanted:
        rows = flatten_system_pages(node)
        if not rows:
            raise InstantiationError("unknown system part")
        wanted = rows[0][0]
    located = locate_owning_part(node, wanted)
    if located is None:
        raise InstantiationError("unknown system part")
    path, part_key = located
    system_node = node if not path else part_at_path(node, path)
    new_system, new_part = fn(system_node, part_key)
    home = part_home_key(path, new_part)
    if path:
        return replace_system_path(node, path, new_system), home
    return new_system, home


def part_artifact_at(artifact: Artifact, page_key: str | None) -> Artifact | None:
    wanted = str(page_key or "").strip()
    if not wanted:
        return None
    for key, _title, child in system_built_parts(artifact):
        if key == wanted:
            return child
    return None


def _walk_children(node: Desc) -> tuple[Desc, ...]:
    if isinstance(node, StructDesc):
        return tuple(child for _name, child in node.fields)
    if isinstance(node, SequenceDesc):
        return node.items
    if isinstance(node, MappingDesc):
        return tuple(child for _key, child in node.entries)
    return ()


def install_all_boundaries(node: Desc, *, depth: int = 0, _seen: frozenset[int] | None = None) -> None:
    """Register every nested meta.boundary. Cycles and depth are rejected; meta_level is unbounded."""
    if node is None:
        return
    if depth > _MAX_DEPTH:
        raise InstantiationError("meta.system nesting too deep")
    seen = _seen or frozenset()
    kind = _kind_of(node)
    mark = id(node)
    if kind in {SYSTEM_KIND, BOUNDARY_KIND, SITE_KIND}:
        if mark in seen:
            raise InstantiationError("meta.system cycle")
        seen = seen | {mark}
    if kind == BOUNDARY_KIND:
        try:
            install_from_desc(node)
        except BoundaryError as exc:
            raise InstantiationError(str(exc)) from exc
    for child in _walk_children(node):
        install_all_boundaries(child, depth=depth + 1, _seen=seen)


def install_system_boundaries(node: Desc, *, depth: int = 0) -> None:
    """Register every meta.boundary nested in this description (systems and other structs)."""
    install_all_boundaries(node, depth=depth)


def _kind_of(node: Desc) -> str:
    if not isinstance(node, StructDesc):
        return ""
    kind = dict(node.fields).get("kind")
    if isinstance(kind, AtomDesc) and kind.has_value and isinstance(kind.value, str):
        return kind.value
    return ""


def _string_field(fields: dict[str, Desc], name: str) -> str:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value and node.type_name == "string":
        return str(node.value or "")
    return ""
