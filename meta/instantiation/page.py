"""Render a software.page artifact as local HTML (no user script)."""

from __future__ import annotations

import html
import re
from typing import Any

from meta.boundary import BOUNDARY_KIND, Boundary, boundary_from_desc, boundary_to_desc
from meta.boundary.errors import BoundaryError
from meta.description.composite import MappingDesc, SequenceDesc, StructDesc, sequence, struct
from meta.description.types import AtomDesc, Desc, atom
from meta.instantiation.artifact import TARGET_WEB_BUILD, Artifact, public_url_for_slug, validate_slug
from meta.instantiation.compile import description_from_artifact
from meta.instantiation.errors import InstantiationError
from meta.instantiation.system import (
    SYSTEM_KIND,
    flatten_system_pages,
    flattened_page_key,
    locate_owning_part,
    locate_site_page,
    part_at_path,
    part_home_key,
    prefixed_site_pages,
    rename_system_part,
    replace_system_path,
    resolve_system_part,
    set_part_title,
    system_built_parts,
    system_parts,
)
from meta.simulation import events_from_state, machine_from_desc, machine_to_desc, step
from meta.simulation.errors import SimulationError

PAGE_KIND = "software.page"
SITE_KIND = "software.site"
HREF_HOST = "host"
HREF_FILE = "file"
HREF_PREVIEW = "preview"
_PREVIEW_NAV_JS = (
    "<script>"
    "document.addEventListener('click',function(e){"
    "var a=e.target.closest('a[data-mp-page]');"
    "if(!a)return;"
    "e.preventDefault();"
    "parent.postMessage({source:'zintriq-meta',page:a.getAttribute('data-mp-page')},'*');"
    "});"
    "</script>"
)
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?$")
_ASSET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?\.(png|jpg|jpeg|gif|webp)$")
_MEASURE_MIN, _MEASURE_MAX = 16, 80
_SPACE_MIN, _SPACE_MAX = 8, 96

_PAGE_CSS = """
body{font:15px/1.45 system-ui,sans-serif;margin:var(--mp-space,24px);color:var(--mp-fg,#111);background:var(--mp-bg,#fff);max-width:var(--mp-measure,40rem)}
.mp-kicker{text-transform:uppercase;letter-spacing:.06em;font-size:11px;color:var(--mp-muted,#666)}
.mp-nav{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 1.2rem}
.mp-nav a{color:var(--mp-accent,#06c)}
.mp-img{margin:0 0 1rem}
.mp-img img{max-width:100%;height:auto;display:block}
.mp-nav a[aria-current="page"]{font-weight:600;color:var(--mp-fg,#111);text-decoration:none}
.mp-state{font-size:1.4rem;margin:.2em 0 1em}
.mp-events{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 1.5rem}
.mp-events button{padding:.35rem .7rem}
.mp-body p,.mp-body h2,.mp-body h3,.mp-body ul,.mp-body blockquote,.mp-body pre{margin:0 0 .8rem}
.mp-body ul{padding-left:1.2rem}
.mp-body blockquote{padding:0 0 0 12px;border-left:3px solid var(--mp-accent,#06c);color:var(--mp-muted,#555)}
.mp-body pre{padding:12px;background:var(--mp-muted,#f4f4f4);overflow:auto;font:13px/1.4 ui-monospace,monospace}
.mp-tree{margin:0;padding-left:1.1rem}
.mp-tree>li{margin:.2rem 0}
.mp-bound{margin:0 0 1rem}
.mp-bound dt{color:var(--mp-muted,#666);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:12px 0 2px}
.mp-bound dd{margin:0}
"""


def validate_asset_name(name: str | None) -> str:
    value = str(name or "").strip().lower()
    if not value or "/" in value or "\\" in value or ".." in value or not _ASSET_RE.fullmatch(value):
        raise InstantiationError("image name must be a local png, jpg, gif, or webp file")
    return value


def software_page(
    *,
    title: str,
    body: tuple[str, ...] | list[str] = (),
    theme: dict[str, str | int] | None = None,
) -> StructDesc:
    """Minimal document description for the software.page boundary."""
    items = tuple(atom("string", value=str(item), has_value=True) for item in body)
    fields: dict[str, Desc] = {
        "kind": atom("string", value=PAGE_KIND, has_value=True),
        "title": atom("string", value=str(title), has_value=True),
        "body": sequence(*items),
    }
    theme_node = _theme_desc(theme)
    if theme_node is not None:
        fields["theme"] = theme_node
    return struct(**fields)


def software_site(
    *,
    title: str,
    pages: tuple[tuple[str, str, tuple[str, ...] | list[str]], ...]
    | list[tuple[str, str, tuple[str, ...] | list[str]]] = (),
    theme: dict[str, str | int] | None = None,
) -> StructDesc:
    """Site description: ordered pages with slug keys under one /build/<slug>."""
    nodes = []
    for key, page_title, body in pages:
        items = tuple(atom("string", value=str(item), has_value=True) for item in body)
        nodes.append(
            struct(
                body=sequence(*items),
                key=atom("string", value=validate_slug(key), has_value=True),
                title=atom("string", value=str(page_title), has_value=True),
            )
        )
    if not nodes:
        raise InstantiationError("software.site requires at least one page")
    fields: dict[str, Desc] = {
        "kind": atom("string", value=SITE_KIND, has_value=True),
        "pages": sequence(*nodes),
        "title": atom("string", value=str(title), has_value=True),
    }
    theme_node = _theme_desc(theme)
    if theme_node is not None:
        fields["theme"] = theme_node
    return struct(**fields)


def default_site_desc() -> StructDesc:
    """Starter site shown in the Meta editor when no local draft exists."""
    site = software_site(
        title="Site",
        pages=(
            ("home", "Home", ("Welcome.",)),
            ("about", "About", ("About this system.",)),
        ),
        theme={
            "accent": "#06c",
            "background": "#fff",
            "color": "#111",
            "measure": 40,
            "space": 24,
        },
    )
    return update_page_copy(
        site,
        key="home",
        title="Home",
        blocks=(
            {"kind": "paragraph", "text": "Welcome."},
            {"kind": "heading", "text": "Next"},
            {"kind": "link", "text": "About", "to": "about"},
        ),
    )


def site_pages(node: Desc) -> tuple[tuple[str, str, StructDesc], ...]:
    """(key, title, page-struct) in definition order."""
    if _kind_of(node) != SITE_KIND or not isinstance(node, StructDesc):
        return ()
    pages = dict(node.fields).get("pages")
    if not isinstance(pages, SequenceDesc):
        return ()
    rows = []
    seen: set[str] = set()
    for item in pages.items:
        if not isinstance(item, StructDesc):
            continue
        key = _page_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append((key, _title_for(item, key), item))
    return tuple(rows)


def resolve_site_page(node: Desc, page_key: str | None) -> StructDesc | None:
    rows = site_pages(node)
    if not rows:
        return None
    wanted = str(page_key or "").strip() or "home"
    for key, _title, page in rows:
        if key == wanted:
            return page
    if wanted == "home":
        return rows[0][2]
    return None


_MAX_SITE_PAGES = 32


def add_site_page(
    node: Desc,
    *,
    key: str | None = None,
    title: str = "",
    body: tuple[str, ...] | list[str] = (),
) -> StructDesc:
    """Append one page to a software.site description."""
    if _kind_of(node) != SITE_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("add_site_page requires software.site")
    pages = dict(node.fields).get("pages")
    if not isinstance(pages, SequenceDesc):
        raise InstantiationError("software.site requires pages")
    existing = {item[0] for item in site_pages(node)}
    if len(existing) >= _MAX_SITE_PAGES:
        raise InstantiationError("too many pages")
    wanted = str(key or "").strip()
    slug = validate_slug(wanted) if wanted else _unused_page_key(existing)
    if slug in existing:
        raise InstantiationError("duplicate page key")
    items = tuple(atom("string", value=str(item), has_value=True) for item in body) or (
        atom("string", value="New page.", has_value=True),
    )
    label = str(title or "").strip() or slug.replace("-", " ").title()
    added = struct(
        body=sequence(*items),
        key=atom("string", value=slug, has_value=True),
        title=atom("string", value=label, has_value=True),
    )
    fields = dict(node.fields)
    fields["pages"] = sequence(*pages.items, added)
    return struct(**fields)


def remove_site_page(node: Desc, key: str) -> StructDesc:
    """Drop one page from a software.site; at least one page must remain."""
    if _kind_of(node) != SITE_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("remove_site_page requires software.site")
    pages = dict(node.fields).get("pages")
    if not isinstance(pages, SequenceDesc):
        raise InstantiationError("software.site requires pages")
    slug = validate_slug(str(key or "").strip())
    kept = []
    removed = False
    for item in pages.items:
        if isinstance(item, StructDesc) and _page_key(item) == slug:
            removed = True
            continue
        kept.append(item)
    if not removed:
        raise InstantiationError("unknown site page")
    remaining = [item for item in kept if isinstance(item, StructDesc) and _page_key(item)]
    if not remaining:
        raise InstantiationError("software.site requires at least one page")
    fields = dict(node.fields)
    fields["pages"] = sequence(*kept)
    return struct(**fields)


def page_to_site(node: Desc) -> StructDesc:
    """Wrap a software.page as a one-page software.site (existing copy is home)."""
    if _kind_of(node) != PAGE_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("page_to_site requires software.page")
    fields = dict(node.fields)
    title = _title_for(node, "Site")
    body = fields.get("body")
    if not isinstance(body, SequenceDesc):
        body = sequence()
    home = struct(
        body=body,
        key=atom("string", value="home", has_value=True),
        title=atom("string", value=title, has_value=True),
    )
    site_fields: dict[str, Desc] = {
        "kind": atom("string", value=SITE_KIND, has_value=True),
        "pages": sequence(home),
        "title": atom("string", value=title, has_value=True),
    }
    theme = fields.get("theme")
    if theme is not None:
        site_fields["theme"] = theme
    return struct(**site_fields)


def _promote_page_for_site_op(node: Desc, page_key: str | None) -> tuple[Desc, str | None]:
    kind = _kind_of(node)
    wanted = str(page_key or "").strip()
    if kind == PAGE_KIND:
        return page_to_site(node), wanted or "home"
    if kind != SYSTEM_KIND:
        return node, page_key
    if locate_site_page(node, wanted) is not None:
        return node, page_key
    owning = locate_owning_part(node, wanted)
    if owning is None:
        raise InstantiationError("add_site_page requires software.site")
    sys_path, part_key = owning
    system_node = node if not sys_path else part_at_path(node, sys_path)
    child = None
    for key, _title, item in system_parts(system_node):
        if key == part_key:
            child = item
            break
    if child is None or _kind_of(child) != PAGE_KIND:
        raise InstantiationError("add_site_page requires software.site")
    updated = replace_system_path(system_node, (part_key,), page_to_site(child))
    if sys_path:
        return replace_system_path(node, sys_path, updated), page_key
    return updated, page_key


def apply_site_op(node: Desc, page_key: str | None, fn, *, promote: bool = False) -> tuple[Desc, str]:
    """Run ``fn(site, local_key, prefix) -> (site, local_key)`` on a root or nested site.

    ``prefix`` is empty for a root ``software.site``; otherwise it is the flattened
    system part key that owns the nested site (home pages use that key).
    ``promote=True`` wraps a ``software.page`` (root or system part) as a site first.
    """
    if promote:
        node, page_key = _promote_page_for_site_op(node, page_key)
    kind = _kind_of(node)
    if kind == SITE_KIND:
        site, local = fn(node, str(page_key or "").strip(), "")
        return site, local
    if kind != SYSTEM_KIND:
        raise InstantiationError("add_site_page requires software.site")
    located = locate_site_page(node, page_key)
    if located is None:
        raise InstantiationError("add_site_page requires software.site")
    path, local = located
    site = part_at_path(node, path)
    new_site, new_local = fn(site, local, "-".join(path))
    return replace_system_path(node, path, new_site), flattened_page_key(path, new_site, new_local)


def copy_surface(node: Desc, page_key: str | None) -> str:
    """Which document Apply copy / theme should edit: ``site``, ``page``, ``boundary``, ``system``, or empty."""
    kind = _kind_of(node)
    if kind == SITE_KIND:
        return "site"
    if kind == PAGE_KIND:
        return "page"
    if kind == BOUNDARY_KIND:
        return "boundary"
    if kind != SYSTEM_KIND:
        return ""
    wanted = str(page_key or "").strip()
    if locate_site_page(node, wanted):
        return "site"
    owning = locate_owning_part(node, wanted)
    if owning is None:
        return ""
    sys_path, part_key = owning
    system_node = node if not sys_path else part_at_path(node, sys_path)
    for key, _title, child in system_parts(system_node):
        if key == part_key:
            child_kind = _kind_of(child)
            if child_kind == PAGE_KIND:
                return "page"
            if child_kind == SITE_KIND:
                return "site"
            if child_kind == BOUNDARY_KIND:
                return "boundary"
            if child_kind == SYSTEM_KIND:
                return "system"
            return ""
    return ""


def _parse_meta_level(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise InstantiationError("meta_level must be an integer")
    if isinstance(value, str) and not str(value).strip():
        return None
    try:
        if isinstance(value, float) and value != int(value):
            raise ValueError
        level = int(value)
    except (TypeError, ValueError) as exc:
        raise InstantiationError("meta_level must be an integer") from exc
    return level


def apply_page_part_update(
    node: Desc,
    page_key: str | None,
    *,
    title: str = "",
    body=None,
    blocks=None,
    new_key: str = "",
) -> tuple[Desc, str]:
    """Update copy on a root software.page or a system page part."""
    kind = _kind_of(node)
    if kind == PAGE_KIND:
        updated = update_page_copy(node, title=title, body=body, blocks=blocks)
        return updated, str(page_key or "").strip()
    if kind != SYSTEM_KIND:
        raise InstantiationError("update requires software.page or software.site")
    wanted = str(page_key or "").strip()
    owning = locate_owning_part(node, wanted)
    if owning is None:
        raise InstantiationError("unknown system part")
    sys_path, part_key = owning
    system_node = node if not sys_path else part_at_path(node, sys_path)
    child = None
    for key, _title, item in system_parts(system_node):
        if key == part_key:
            child = item
            break
    if child is None or _kind_of(child) != PAGE_KIND:
        raise InstantiationError("update requires software.page")
    child = update_page_copy(child, title=title, body=body, blocks=blocks)
    label = str(title or "").strip() or _title_for(child, part_key)
    system_node = replace_system_path(system_node, (part_key,), child)
    system_node = set_part_title(system_node, part_key, label)
    typed = typed_local_key(str(new_key or ""), part_key, "-".join(sys_path))
    if typed and typed != part_key:
        system_node = rename_system_part(system_node, part_key, typed)
        part_key = typed
    home = part_home_key(sys_path, part_key)
    if sys_path:
        return replace_system_path(node, sys_path, system_node), home
    return system_node, home


def apply_boundary_part_update(
    node: Desc,
    page_key: str | None,
    *,
    title: str = "",
    new_key: str = "",
    bound_id: str = "",
    surface_kind: str = "",
    target: str = "",
    meta_level=None,
) -> tuple[Desc, str]:
    """Update name, id, surface, target, meta_level (and optional system part key) on a meta.boundary."""
    label = str(title or "").strip()
    if not label:
        raise InstantiationError("title required")
    if len(label) > _TITLE_MAX:
        raise InstantiationError("title too long")
    level_override = _parse_meta_level(meta_level)

    def _named(child: Desc) -> Desc:
        if _kind_of(child) != BOUNDARY_KIND:
            raise InstantiationError("update requires meta.boundary")
        try:
            described = boundary_from_desc(child)
            rebuilt = boundary_to_desc(
                Boundary(
                    id=str(bound_id or "").strip() or described.id,
                    name=label,
                    kind=str(surface_kind or "").strip() or described.kind,
                    instantiation_target=str(target or "").strip() or described.instantiation_target,
                    meta_level=described.meta_level if level_override is None else level_override,
                )
            )
            boundary_from_desc(rebuilt)
        except BoundaryError as exc:
            raise InstantiationError(str(exc)) from exc
        return rebuilt

    kind = _kind_of(node)
    if kind == BOUNDARY_KIND:
        return _named(node), str(page_key or "").strip()
    if kind != SYSTEM_KIND:
        raise InstantiationError("update requires meta.boundary")
    wanted = str(page_key or "").strip()
    owning = locate_owning_part(node, wanted)
    if owning is None:
        raise InstantiationError("unknown system part")
    sys_path, part_key = owning
    system_node = node if not sys_path else part_at_path(node, sys_path)
    child = None
    for key, _title, item in system_parts(system_node):
        if key == part_key:
            child = item
            break
    if child is None:
        raise InstantiationError("unknown system part")
    child = _named(child)
    system_node = replace_system_path(system_node, (part_key,), child)
    system_node = set_part_title(system_node, part_key, label)
    typed = typed_local_key(str(new_key or ""), part_key, "-".join(sys_path))
    if typed and typed != part_key:
        system_node = rename_system_part(system_node, part_key, typed)
        part_key = typed
    home = part_home_key(sys_path, part_key)
    if sys_path:
        return replace_system_path(node, sys_path, system_node), home
    return system_node, home


def apply_system_node_update(
    node: Desc,
    page_key: str | None,
    *,
    title: str = "",
    new_key: str = "",
) -> tuple[Desc, str]:
    """Update title (and optional part key) on a nested meta.system part."""
    label = str(title or "").strip()
    if not label:
        raise InstantiationError("title required")
    if len(label) > _TITLE_MAX:
        raise InstantiationError("title too long")
    kind = _kind_of(node)
    if kind != SYSTEM_KIND:
        raise InstantiationError("update requires meta.system")
    wanted = str(page_key or "").strip()
    owning = locate_owning_part(node, wanted)
    if owning is None:
        raise InstantiationError("unknown system part")
    sys_path, part_key = owning
    system_node = node if not sys_path else part_at_path(node, sys_path)
    child = None
    for key, _title, item in system_parts(system_node):
        if key == part_key:
            child = item
            break
    if child is None or _kind_of(child) != SYSTEM_KIND or not isinstance(child, StructDesc):
        raise InstantiationError("update requires meta.system")
    fields = dict(child.fields)
    fields["title"] = atom("string", value=label, has_value=True)
    child = struct(**fields)
    system_node = replace_system_path(system_node, (part_key,), child)
    system_node = set_part_title(system_node, part_key, label)
    typed = typed_local_key(str(new_key or ""), part_key, "-".join(sys_path))
    if typed and typed != part_key:
        system_node = rename_system_part(system_node, part_key, typed)
        part_key = typed
    home = part_home_key(sys_path, part_key)
    if sys_path:
        return replace_system_path(node, sys_path, system_node), home
    return system_node, home


def apply_step_at_key(node: Desc, page_key: str | None, event: str) -> tuple[Desc, str]:
    """Advance the machine on the selected flatten key, else the root description."""
    wanted = str(page_key or "").strip()
    located = locate_site_page(node, wanted) if wanted else None
    if located is not None:
        path, local = located
        site = node if not path else part_at_path(node, path)
        page = resolve_site_page(site, local)
        if page is not None:
            try:
                advanced = machine_to_desc(step(machine_from_desc(page), str(event or "")))
            except SimulationError:
                advanced = None
            if advanced is not None:
                updated_site = _replace_page(site, local, lambda _page: advanced)
                if not path:
                    return updated_site, local
                return replace_system_path(node, path, updated_site), flattened_page_key(
                    path, updated_site, local
                )
    if _kind_of(node) == SYSTEM_KIND and wanted:
        owning = locate_owning_part(node, wanted)
        if owning is not None:
            sys_path, part_key = owning
            system_node = node if not sys_path else part_at_path(node, sys_path)
            child = None
            for key, _title, item in system_parts(system_node):
                if key == part_key:
                    child = item
                    break
            if child is not None:
                try:
                    advanced = machine_to_desc(step(machine_from_desc(child), str(event or "")))
                except SimulationError:
                    advanced = None
                if advanced is not None:
                    system_node = replace_system_path(system_node, (part_key,), advanced)
                    home = part_home_key(sys_path, part_key)
                    if sys_path:
                        return replace_system_path(node, sys_path, system_node), home
                    return system_node, home
    try:
        return machine_to_desc(step(machine_from_desc(node), str(event or ""))), wanted
    except SimulationError as exc:
        raise InstantiationError(str(exc)) from exc


def apply_page_part_theme(
    node: Desc,
    page_key: str | None,
    theme: dict | None,
    *,
    scope: str = "site",
) -> tuple[Desc, str]:
    """Replace theme on a root software.page or a system page part."""
    kind = _kind_of(node)
    if kind == PAGE_KIND:
        updated = update_page_theme(node, theme, scope=scope)
        return updated, str(page_key or "").strip()
    if kind != SYSTEM_KIND:
        raise InstantiationError("theme requires software.page or software.site")
    wanted = str(page_key or "").strip()
    owning = locate_owning_part(node, wanted)
    if owning is None:
        raise InstantiationError("unknown system part")
    sys_path, part_key = owning
    system_node = node if not sys_path else part_at_path(node, sys_path)
    child = None
    for key, _title, item in system_parts(system_node):
        if key == part_key:
            child = item
            break
    if child is None or _kind_of(child) != PAGE_KIND:
        raise InstantiationError("theme requires software.page")
    child = update_page_theme(child, theme, scope=scope)
    system_node = replace_system_path(system_node, (part_key,), child)
    home = part_home_key(sys_path, part_key)
    if sys_path:
        return replace_system_path(node, sys_path, system_node), home
    return system_node, home


def typed_local_key(typed: str, local: str, prefix: str) -> str:
    """Map an editor page-key field (flattened or local) back onto the site."""
    wanted = str(typed or "").strip()
    if not wanted:
        return local
    if prefix:
        if wanted == prefix:
            return local
        lead = prefix + "-"
        if wanted.startswith(lead):
            wanted = wanted[len(lead):]
            if not wanted:
                return local
    return wanted


def duplicate_site_page(node: Desc, key: str) -> StructDesc:
    """Copy one site page after the source, with a new key."""
    if _kind_of(node) != SITE_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("duplicate_site_page requires software.site")
    pages = dict(node.fields).get("pages")
    if not isinstance(pages, SequenceDesc):
        raise InstantiationError("software.site requires pages")
    slug = validate_slug(str(key or "").strip())
    existing = {item[0] for item in site_pages(node)}
    if slug not in existing:
        raise InstantiationError("unknown site page")
    if len(existing) >= _MAX_SITE_PAGES:
        raise InstantiationError("too many pages")
    source = None
    label = slug
    for item_key, title, page in site_pages(node):
        if item_key == slug:
            source = page
            label = title
            break
    if source is None:
        raise InstantiationError("unknown site page")
    new_key = _copy_page_key(slug, existing)
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
    for item in pages.items:
        rebuilt.append(item)
        if not inserted and isinstance(item, StructDesc) and _page_key(item) == slug:
            rebuilt.append(cloned)
            inserted = True
    if not inserted:
        rebuilt.append(cloned)
    root = dict(node.fields)
    root["pages"] = sequence(*rebuilt)
    return struct(**root)


_TITLE_MAX = 120
_PARA_MAX = 4000
_PARA_COUNT = 40


def document_copy(node: Desc, page_key: str | None = None) -> tuple[str, tuple[str, ...]] | None:
    """Title and paragraph strings for the selected page (or software.page)."""
    selected = _copy_target(node, page_key)
    if selected is None:
        return None
    key = _page_key(selected) if _kind_of(node) == SITE_KIND else ""
    if _kind_of(selected) == BOUNDARY_KIND:
        try:
            name = boundary_from_desc(selected).name
        except BoundaryError:
            name = ""
        return name or key or "boundary", ()
    return _title_for(selected, key or "page"), _body_texts(selected)


def boundary_copy(node: Desc, page_key: str | None = None) -> dict[str, str | int] | None:
    """Id, name, surface, and target for the selected meta.boundary."""
    selected = _copy_target(node, page_key)
    if selected is None or _kind_of(selected) != BOUNDARY_KIND:
        return None
    try:
        described = boundary_from_desc(selected)
    except BoundaryError:
        return None
    return {
        "id": described.id,
        "meta_level": described.meta_level,
        "name": described.name,
        "surface": described.kind,
        "target": described.instantiation_target,
    }


def page_blocks(node: Desc, page_key: str | None = None) -> list[dict] | None:
    """Structured body blocks: paragraph / heading / link / list / quote / image / code."""
    selected = _copy_target(node, page_key)
    if selected is None:
        return None
    return [dict(item) for item in _blocks_from_body(selected)]


def update_page_copy(
    node: Desc,
    *,
    key: str | None = None,
    title: str | None = None,
    body: str | list[str] | tuple[str, ...] | None = None,
    blocks: list | tuple | None = None,
) -> StructDesc:
    """Replace title and/or body on software.page or one site page."""
    if title is None and body is None and blocks is None:
        raise InstantiationError("title or body required")
    label = None
    if title is not None:
        label = str(title).strip()
        if not label:
            raise InstantiationError("title required")
        if len(label) > _TITLE_MAX:
            raise InstantiationError("title too long")
    paras = None
    if blocks is not None:
        paras = _blocks_sequence(blocks)
    elif body is not None:
        paras = _body_sequence(body)
    return _replace_page(node, key, lambda page: _with_copy(page, label, paras))


def move_site_page(node: Desc, key: str, *, delta: int) -> StructDesc:
    """Swap a site page with its neighbor. delta is -1 or 1."""
    if delta not in (-1, 1):
        raise InstantiationError("delta must be -1 or 1")
    if _kind_of(node) != SITE_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("move_site_page requires software.site")
    rows = list(site_pages(node))
    slug = validate_slug(str(key or "").strip())
    keys = [item[0] for item in rows]
    try:
        index = keys.index(slug)
    except ValueError as exc:
        raise InstantiationError("unknown site page") from exc
    other = index + delta
    if other < 0 or other >= len(keys):
        return node
    items = [page for _key, _title, page in rows]
    items[index], items[other] = items[other], items[index]
    fields = dict(node.fields)
    fields["pages"] = sequence(*items)
    return struct(**fields)


def site_title(node: Desc, page_key: str | None = None) -> str | None:
    """Root title of software.site, or the nested site that owns ``page_key``."""
    if _kind_of(node) == SITE_KIND and isinstance(node, StructDesc):
        return _title_for(node, "Site")
    if _kind_of(node) != SYSTEM_KIND:
        return None
    located = locate_site_page(node, page_key)
    if located is None:
        return None
    site = part_at_path(node, located[0])
    if not isinstance(site, StructDesc):
        return None
    return _title_for(site, "Site")


def update_site_title(node: Desc, title: str) -> StructDesc:
    """Replace the software.site root title (not a page title)."""
    if _kind_of(node) != SITE_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("update_site_title requires software.site")
    label = str(title).strip()
    if not label:
        raise InstantiationError("title required")
    if len(label) > _TITLE_MAX:
        raise InstantiationError("title too long")
    fields = dict(node.fields)
    fields["title"] = atom("string", value=label, has_value=True)
    return struct(**fields)


def rename_site_page(node: Desc, key: str, new_key: str) -> StructDesc:
    """Rename a page key and rewrite matching body `to` links."""
    if _kind_of(node) != SITE_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("rename_site_page requires software.site")
    old = validate_slug(str(key or "").strip())
    new = validate_slug(str(new_key or "").strip())
    if old == new:
        return node
    existing = {item[0] for item in site_pages(node)}
    if old not in existing:
        raise InstantiationError("unknown site page")
    if new in existing:
        raise InstantiationError("duplicate page key")
    pages = dict(node.fields).get("pages")
    if not isinstance(pages, SequenceDesc):
        raise InstantiationError("software.site requires pages")
    rebuilt = []
    for item in pages.items:
        if not isinstance(item, StructDesc):
            rebuilt.append(item)
            continue
        page = item
        if _page_key(page) == old:
            fields = dict(page.fields)
            fields["key"] = atom("string", value=new, has_value=True)
            page = struct(**fields)
        rebuilt.append(_rewrite_to_links(page, old, new))
    fields = dict(node.fields)
    fields["pages"] = sequence(*rebuilt)
    return struct(**fields)


def _rewrite_to_links(page: StructDesc, old: str, new: str) -> StructDesc:
    body = dict(page.fields).get("body")
    if not isinstance(body, SequenceDesc):
        return page
    items = []
    changed = False
    for item in body.items:
        if isinstance(item, StructDesc) and _string_field(dict(item.fields), "to") == old:
            fields = dict(item.fields)
            fields["to"] = atom("string", value=new, has_value=True)
            items.append(struct(**fields))
            changed = True
        else:
            items.append(item)
    if not changed:
        return page
    fields = dict(page.fields)
    fields["body"] = sequence(*items)
    return struct(**fields)


def theme_copy(
    node: Desc,
    page_key: str | None = None,
    *,
    scope: str = "site",
) -> dict[str, str | int] | None:
    """Sanitized theme fields. scope=page reads the selected page (inherit if empty)."""
    wanted = str(scope or "site").strip() or "site"
    if wanted not in {"site", "page"}:
        wanted = "site"
    if _kind_of(node) == SYSTEM_KIND:
        located = locate_site_page(node, page_key)
        if located is None:
            found = resolve_system_part(node, page_key)
            if found is not None and isinstance(found[2], StructDesc):
                child_kind = _kind_of(found[2])
                if child_kind in {PAGE_KIND, SITE_KIND}:
                    return _theme_fields_dict(found[2])
            return None
        site = part_at_path(node, located[0])
        return theme_copy(site, located[1], scope=wanted)
    if _kind_of(node) not in {PAGE_KIND, SITE_KIND} or not isinstance(node, StructDesc):
        return None
    target = node
    if wanted == "page" and _kind_of(node) == SITE_KIND:
        selected = resolve_site_page(node, page_key)
        if selected is None:
            return None
        target = selected
    return _theme_fields_dict(target)


def update_page_theme(
    node: Desc,
    theme: dict | None,
    *,
    key: str | None = None,
    scope: str = "site",
) -> StructDesc:
    """Replace theme on site root (scope=site) or one page (scope=page)."""
    if _kind_of(node) not in {PAGE_KIND, SITE_KIND} or not isinstance(node, StructDesc):
        raise InstantiationError("theme requires software.page or software.site")
    wanted = str(scope or "site").strip() or "site"
    if wanted not in {"site", "page"}:
        raise InstantiationError("theme scope must be site or page")
    node_theme = _theme_desc(_cleaned_theme(theme))
    if wanted == "site" or _kind_of(node) == PAGE_KIND:
        return _with_theme(node, node_theme)
    return _replace_page(node, key, lambda page: _with_theme(page, node_theme))


def _cleaned_theme(theme: dict | None) -> dict[str, str | int]:
    raw = theme if isinstance(theme, dict) else {}
    cleaned: dict[str, str | int] = {}
    for key in ("accent", "background", "color"):
        if key not in raw or raw[key] in (None, ""):
            continue
        hex_value = _hex_color(str(raw[key]).strip())
        if not hex_value:
            raise InstantiationError("theme colors must be hex")
        cleaned[key] = hex_value
    for key, lo, hi in (("measure", _MEASURE_MIN, _MEASURE_MAX), ("space", _SPACE_MIN, _SPACE_MAX)):
        if key not in raw or raw[key] in (None, ""):
            continue
        val = raw[key]
        if isinstance(val, bool):
            raise InstantiationError("theme layout must be int")
        try:
            number = int(val)
        except (TypeError, ValueError):
            raise InstantiationError("theme layout must be int") from None
        if number < lo or number > hi:
            raise InstantiationError("theme layout out of range")
        cleaned[key] = number
    return cleaned


def _theme_fields_dict(node: StructDesc) -> dict[str, str | int]:
    out: dict[str, str | int] = {
        "accent": "",
        "background": "",
        "color": "",
        "measure": "",
        "space": "",
    }
    theme = dict(node.fields).get("theme")
    if not isinstance(theme, StructDesc):
        return out
    fields = dict(theme.fields)
    for key in ("accent", "background", "color"):
        hex_value = _hex_color(_string_field(fields, key))
        if hex_value:
            out[key] = hex_value
    measure = _int_field(fields, "measure", lo=_MEASURE_MIN, hi=_MEASURE_MAX)
    if measure is not None:
        out["measure"] = measure
    space = _int_field(fields, "space", lo=_SPACE_MIN, hi=_SPACE_MAX)
    if space is not None:
        out["space"] = space
    return out


def _replace_page(node: Desc, key: str | None, fn) -> StructDesc:
    kind = _kind_of(node)
    if kind == PAGE_KIND and isinstance(node, StructDesc):
        return fn(node)
    if kind != SITE_KIND or not isinstance(node, StructDesc):
        raise InstantiationError("update requires software.page or software.site")
    pages = dict(node.fields).get("pages")
    if not isinstance(pages, SequenceDesc):
        raise InstantiationError("software.site requires pages")
    slug = validate_slug(str(key or "").strip())
    rebuilt = []
    found = False
    for item in pages.items:
        if isinstance(item, StructDesc) and _page_key(item) == slug:
            rebuilt.append(fn(item))
            found = True
        else:
            rebuilt.append(item)
    if not found:
        raise InstantiationError("unknown site page")
    fields = dict(node.fields)
    fields["pages"] = sequence(*rebuilt)
    return struct(**fields)


def _copy_target(node: Desc, page_key: str | None) -> StructDesc | None:
    kind = _kind_of(node)
    if kind == PAGE_KIND and isinstance(node, StructDesc):
        return node
    if kind == BOUNDARY_KIND and isinstance(node, StructDesc):
        return node
    if kind == SITE_KIND:
        return resolve_site_page(node, page_key)
    if kind == SYSTEM_KIND:
        found = resolve_system_part(node, page_key)
        if found is not None and isinstance(found[2], StructDesc):
            return found[2]
    return None


def _body_texts(node: StructDesc) -> tuple[str, ...]:
    body = dict(node.fields).get("body")
    if not isinstance(body, SequenceDesc):
        return ()
    texts: list[str] = []
    for item in body.items:
        if isinstance(item, AtomDesc) and item.has_value:
            texts.append(str(item.value))
            continue
        if isinstance(item, SequenceDesc):
            for child in item.items:
                if isinstance(child, AtomDesc) and child.has_value:
                    texts.append(str(child.value))
            continue
        if isinstance(item, StructDesc):
            fields = dict(item.fields)
            heading = _string_field(fields, "heading")
            text = _string_field(fields, "text")
            quote = _string_field(fields, "quote")
            code = _string_field(fields, "code")
            if heading:
                texts.append(heading)
            if quote:
                texts.append(quote)
            if code:
                texts.append(code)
            if text:
                texts.append(text)
    return tuple(texts)


def _blocks_from_body(node: StructDesc) -> tuple[dict[str, str], ...]:
    body = dict(node.fields).get("body")
    if not isinstance(body, SequenceDesc):
        return ()
    blocks: list[dict[str, str]] = []
    for item in body.items:
        if isinstance(item, AtomDesc) and item.has_value:
            blocks.append({"kind": "paragraph", "text": str(item.value)})
            continue
        if isinstance(item, SequenceDesc):
            lines = [
                str(child.value).strip()
                for child in item.items
                if isinstance(child, AtomDesc) and child.has_value and str(child.value).strip()
            ]
            if lines:
                blocks.append({"kind": "list", "items": lines})
            continue
        if not isinstance(item, StructDesc):
            continue
        fields = dict(item.fields)
        target = _string_field(fields, "to")
        heading = _string_field(fields, "heading")
        text = _string_field(fields, "text")
        src = _string_field(fields, "src")
        quote = _string_field(fields, "quote")
        code = _string_field(fields, "code")
        if src:
            try:
                name = validate_asset_name(src)
            except InstantiationError:
                name = ""
            if name:
                blocks.append({"kind": "image", "src": name, "text": text})
                continue
        if target:
            try:
                slug = validate_slug(target)
            except InstantiationError:
                slug = ""
            if slug:
                blocks.append({"kind": "link", "text": text or slug, "to": slug})
                continue
        items_field = fields.get("items")
        if isinstance(items_field, SequenceDesc):
            lines = [
                str(child.value).strip()
                for child in items_field.items
                if isinstance(child, AtomDesc) and child.has_value and str(child.value).strip()
            ]
            if lines:
                blocks.append({"kind": "list", "items": lines})
            continue
        if quote:
            blocks.append({"kind": "quote", "text": quote})
            continue
        if code:
            blocks.append({"kind": "code", "text": code})
            continue
        if heading:
            block = {"kind": "heading", "text": heading}
            level = _int_field(fields, "level", lo=2, hi=3)
            if level == 3:
                block["level"] = 3
            blocks.append(block)
        if text:
            blocks.append({"kind": "paragraph", "text": text})
    return tuple(blocks)


def _blocks_sequence(blocks: list | tuple) -> SequenceDesc:
    if not isinstance(blocks, (list, tuple)):
        raise InstantiationError("blocks must be a list")
    if len(blocks) > _PARA_COUNT:
        raise InstantiationError("too many paragraphs")
    nodes: list[Desc] = []
    for item in blocks:
        if not isinstance(item, dict):
            raise InstantiationError("block must be an object")
        kind = str(item.get("kind") or "paragraph").strip()
        text = str(item.get("text") or "").strip()
        if len(text) > _PARA_MAX:
            raise InstantiationError("paragraph too long")
        if kind == "paragraph":
            if text:
                nodes.append(atom("string", value=text, has_value=True))
        elif kind == "heading":
            if text:
                level = _heading_level(item.get("level"))
                fields = {"heading": atom("string", value=text, has_value=True)}
                if level == 3:
                    fields["level"] = atom("int", value=3, has_value=True)
                nodes.append(struct(**fields))
        elif kind == "quote":
            if text:
                nodes.append(struct(quote=atom("string", value=text, has_value=True)))
        elif kind == "code":
            if text:
                nodes.append(struct(code=atom("string", value=text, has_value=True)))
        elif kind == "link":
            slug = validate_slug(str(item.get("to") or "").strip())
            label = text or slug
            nodes.append(
                struct(
                    text=atom("string", value=label, has_value=True),
                    to=atom("string", value=slug, has_value=True),
                )
            )
        elif kind == "image":
            name = validate_asset_name(str(item.get("src") or "").strip())
            nodes.append(
                struct(
                    src=atom("string", value=name, has_value=True),
                    text=atom("string", value=text, has_value=True),
                )
            )
        elif kind == "list":
            raw = item.get("items")
            if isinstance(raw, str):
                lines = [part.strip() for part in raw.replace("\r\n", "\n").split("\n")]
            elif isinstance(raw, (list, tuple)):
                lines = [str(part).strip() for part in raw]
            else:
                lines = [part.strip() for part in text.replace("\r\n", "\n").split("\n")]
            lines = [part for part in lines if part]
            if len(lines) > _PARA_COUNT:
                raise InstantiationError("too many paragraphs")
            for part in lines:
                if len(part) > _PARA_MAX:
                    raise InstantiationError("paragraph too long")
            if lines:
                nodes.append(
                    sequence(*(atom("string", value=part, has_value=True) for part in lines))
                )
        else:
            raise InstantiationError("unknown block kind")
    return sequence(*nodes)


def _body_sequence(body: str | list[str] | tuple[str, ...]) -> SequenceDesc:
    if isinstance(body, str):
        parts = [item.strip() for item in body.replace("\r\n", "\n").split("\n")]
    elif isinstance(body, (list, tuple)):
        parts = [str(item).strip() for item in body]
    else:
        raise InstantiationError("body must be text")
    parts = [item for item in parts if item]
    if len(parts) > _PARA_COUNT:
        raise InstantiationError("too many paragraphs")
    for item in parts:
        if len(item) > _PARA_MAX:
            raise InstantiationError("paragraph too long")
    atoms = tuple(atom("string", value=item, has_value=True) for item in parts)
    return sequence(*atoms)


def _with_copy(page: StructDesc, title: str | None, body: SequenceDesc | None) -> StructDesc:
    fields = dict(page.fields)
    if title is not None:
        fields["title"] = atom("string", value=title, has_value=True)
    if body is not None:
        fields["body"] = body
    return struct(**fields)


def _with_theme(page: StructDesc, theme: StructDesc | None) -> StructDesc:
    fields = dict(page.fields)
    if theme is None:
        fields.pop("theme", None)
    else:
        fields["theme"] = theme
    return struct(**fields)


def _unused_page_key(existing: set[str]) -> str:
    if "page" not in existing:
        return "page"
    n = 2
    while n <= _MAX_SITE_PAGES + 1:
        candidate = f"page-{n}"
        if candidate not in existing:
            return candidate
        n += 1
    raise InstantiationError("too many pages")


def _copy_page_key(base: str, existing: set[str]) -> str:
    n = 2
    while n <= _MAX_SITE_PAGES + 1:
        candidate = f"{base}-{n}"
        try:
            slug = validate_slug(candidate)
        except InstantiationError:
            return _unused_page_key(existing)
        if slug not in existing:
            return slug
        n += 1
    return _unused_page_key(existing)


def page_href(base: str, key: str, *, href_style: str = HREF_HOST) -> str:
    clean = validate_slug(key)
    if href_style == HREF_FILE:
        return f"{clean}.html"
    if href_style == HREF_PREVIEW:
        return f"#mp-{clean}"
    return f"{base}/{clean}"


def rendered_site_files(artifact: Artifact) -> tuple[tuple[str, str], ...]:
    """Static files for a web_build artifact (relative links, no step forms)."""
    desc = description_from_artifact(artifact)
    built = system_built_parts(artifact)
    files: list[tuple[str, str]] = []
    by_name: dict[str, str] = {}
    if built:
        for key, _title, child in built:
            if child.target != TARGET_WEB_BUILD:
                files.append((f"{key}.json", child.payload))
                continue
            keys = [key]
            try:
                child_desc = description_from_artifact(child)
            except InstantiationError:
                child_desc = None
            if child_desc is not None:
                expanded = prefixed_site_pages(key, child_desc)
                if expanded:
                    keys = [item[0] for item in expanded]
            for page_full in keys:
                name = f"{page_full}.html"
                html_doc = render_software_page(artifact, page_key=page_full, href_style=HREF_FILE)
                files.append((name, html_doc))
                by_name[name] = html_doc
    else:
        rows = site_pages(desc)
        if not rows:
            rows = flatten_system_pages(desc)
        keys = [key for key, _title, _page in rows] or ["home"]
        for key in keys:
            name = f"{key}.html"
            html_doc = render_software_page(artifact, page_key=key, href_style=HREF_FILE)
            files.append((name, html_doc))
            by_name[name] = html_doc
    if by_name:
        index_name = "home.html" if "home.html" in by_name else next(iter(by_name))
        files.append(("index.html", by_name[index_name]))
    elif files:
        files.append(("index.html", files[0][1]))
    return tuple(files)


def render_software_page(
    artifact: Artifact,
    *,
    step_action: str = "",
    csrf_token: str = "",
    page_key: str | None = None,
    href_style: str = HREF_HOST,
    asset_href=None,
) -> str:
    """Compile artifact payload into a static HTML document."""
    if artifact.target != TARGET_WEB_BUILD:
        raise InstantiationError("only web_build artifacts render as software.page")
    desc = description_from_artifact(artifact)
    slug = html.escape(artifact.slug or "page")
    kind = _kind_of(desc)
    base = artifact.public_url or public_url_for_slug(artifact.slug or "page")
    selected = desc
    current_key = ""
    system_rows = ()
    if kind == SITE_KIND:
        selected = resolve_site_page(desc, page_key)
        if selected is None:
            raise InstantiationError("unknown site page")
        current_key = _page_key(selected)
    elif kind == SYSTEM_KIND:
        found = resolve_system_part(desc, page_key)
        if found is None:
            raise InstantiationError("unknown system part")
        current_key, part_title, selected = found
        system_rows = flatten_system_pages(desc)
        title_text = part_title
    elif page_key and page_key not in {"", "home"}:
        raise InstantiationError("unknown site page")
    if kind != SYSTEM_KIND:
        title_text = _title_for(selected, current_key or artifact.slug or "page")
    bound_id = artifact.boundary_id or "software.page"
    selected_kind = _kind_of(selected)
    if (
        not selected_kind
        and isinstance(selected, StructDesc)
        and isinstance(dict(selected.fields).get("body"), SequenceDesc)
    ):
        selected_kind = PAGE_KIND
    if selected_kind == BOUNDARY_KIND:
        try:
            described = boundary_from_desc(selected)
            bound_id = described.id
            if kind != SYSTEM_KIND:
                title_text = described.name or described.id
        except BoundaryError:
            pass
    title = html.escape(title_text)
    state = ""
    events: tuple[str, ...] = ()
    try:
        machine = machine_from_desc(selected)
        state = machine.state
        events = events_from_state(machine)
    except SimulationError:
        pass
    forms = href_style == HREF_HOST
    theme = _merged_theme(desc, selected)
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{title}</title>",
        f"<style>{_PAGE_CSS}</style></head>",
        f'<body class="mp-page" data-boundary="{html.escape(bound_id)}" data-slug="{slug}"',
        f' data-page-kind="{html.escape(kind or "desc")}"',
    ]
    if kind == SYSTEM_KIND and selected_kind:
        parts.append(f' data-part-kind="{html.escape(selected_kind)}"')
    if current_key:
        parts.append(f' data-page-key="{html.escape(current_key)}"')
    if state:
        parts.append(f' data-machine-state="{html.escape(state)}"')
    if theme:
        parts.append(f' data-theme="1" style="{html.escape(_theme_style(theme))}"')
    parts.append(">")
    parts.append(f'<p class="mp-kicker">{html.escape((selected_kind if kind == SYSTEM_KIND else kind) or "software.page")}</p>')
    if kind == SITE_KIND:
        parts.append(_render_nav(site_pages(desc), base, current_key, href_style=href_style))
    elif kind == SYSTEM_KIND:
        parts.append(_render_nav(system_rows, base, current_key, href_style=href_style))
    parts.append(f"<h1>{title}</h1>")
    if state:
        parts.append(f'<p class="mp-state">State {html.escape(state)}</p>')
    if forms and step_action and events:
        parts.append('<div class="mp-events">')
        for event in events:
            parts.append(_event_form(step_action, event, csrf_token))
        parts.append("</div>")
    world_kind = selected_kind if kind == SYSTEM_KIND else kind
    from meta.runtime.world import is_world_kind, render_world

    if is_world_kind(world_kind) or is_world_kind(selected_kind):
        parts.append(render_world(selected))
    elif kind in {PAGE_KIND, SITE_KIND}:
        parts.append(
            _render_document(selected, base=base, href_style=href_style, asset_href=asset_href)
        )
    elif kind == SYSTEM_KIND:
        parts.append(
            _render_system_part(
                selected,
                prefix=current_key,
                base=base,
                href_style=href_style,
                asset_href=asset_href,
            )
        )
    elif kind == BOUNDARY_KIND:
        parts.append(_render_boundary(desc))
    else:
        parts.append(_render_desc(selected))
    if href_style == HREF_PREVIEW:
        parts.append(_PREVIEW_NAV_JS)
    parts.append("</body></html>")
    return "".join(parts)


def _render_system_part(
    node: Desc,
    *,
    prefix: str,
    base: str,
    href_style: str,
    asset_href=None,
) -> str:
    kind = _kind_of(node)
    from meta.runtime.world import is_world_kind, render_world

    if is_world_kind(kind):
        return render_world(node)
    if kind in {SITE_KIND, SYSTEM_KIND, BOUNDARY_KIND}:
        pass
    elif isinstance(node, StructDesc) and (
        kind == PAGE_KIND or isinstance(dict(node.fields).get("body"), SequenceDesc)
    ):
        return _render_document(node, base=base, href_style=href_style, asset_href=asset_href)
    if kind == SITE_KIND and isinstance(node, StructDesc):
        links = []
        for full, title, _page in prefixed_site_pages(prefix, node):
            links.append(_internal_anchor(full, title or full, base=base, href_style=href_style))
        home = resolve_site_page(node, None)
        body = ""
        if home is not None:
            body = _render_document(home, base=base, href_style=href_style, asset_href=asset_href)
        if links:
            body = f'<nav class="mp-nav">{"".join(links)}</nav>{body}'
        return body or _render_desc(node)
    if kind == BOUNDARY_KIND:
        return _render_boundary(node)
    if kind == SYSTEM_KIND:
        links = []
        for key, title, _child in system_parts(node):
            full = f"{prefix}-{key}" if prefix else key
            try:
                full = validate_slug(full)
            except InstantiationError:
                continue
            links.append(_internal_anchor(full, title or key, base=base, href_style=href_style))
        if not links:
            return "<p>Empty system.</p>"
        return f'<ul class="mp-list">{"".join(f"<li>{item}</li>" for item in links)}</ul>'
    return _render_desc(node)


def _render_boundary(node: Desc) -> str:
    try:
        boundary = boundary_from_desc(node)
    except BoundaryError:
        return _render_desc(node)
    ident = html.escape(boundary.id)
    name = html.escape(boundary.name)
    surface = html.escape(boundary.kind)
    target = html.escape(boundary.instantiation_target)
    level = html.escape(str(boundary.meta_level))
    return (
        '<dl class="mp-bound">'
        f"<dt>id</dt><dd>{ident}</dd>"
        f"<dt>name</dt><dd>{name}</dd>"
        f"<dt>surface</dt><dd>{surface}</dd>"
        f"<dt>instantiates to</dt><dd>{target}</dd>"
        f"<dt>meta_level</dt><dd>{level}</dd>"
        "</dl>"
        f"<p>This boundary is instantiated. Other descriptions may instantiate through "
        f"<code>{ident}</code> onto <code>{target}</code>.</p>"
    )


def _kind_of(node: Desc) -> str:
    if not isinstance(node, StructDesc):
        return ""
    kind = dict(node.fields).get("kind")
    if isinstance(kind, AtomDesc) and kind.has_value and isinstance(kind.value, str):
        return kind.value
    return ""


def _title_for(node: Desc, fallback: str) -> str:
    if not isinstance(node, StructDesc):
        return fallback
    title = _string_field(dict(node.fields), "title")
    return title or fallback


def _string_field(fields: dict[str, Desc], name: str) -> str:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value and node.type_name == "string":
        return str(node.value or "")
    return ""


def _theme_desc(theme: dict[str, str | int] | None) -> StructDesc | None:
    if not theme:
        return None
    fields: dict[str, Desc] = {}
    for key in ("accent", "background", "color"):
        if key in theme and theme[key] is not None:
            fields[key] = atom("string", value=str(theme[key]), has_value=True)
    for key, lo, hi in (("measure", _MEASURE_MIN, _MEASURE_MAX), ("space", _SPACE_MIN, _SPACE_MAX)):
        raw = theme.get(key)
        if isinstance(raw, bool) or not isinstance(raw, int):
            continue
        if lo <= raw <= hi:
            fields[key] = atom("int", value=raw, has_value=True)
    return struct(**fields) if fields else None


def _hex_color(value: str) -> str:
    text = str(value or "").strip()
    if _HEX_COLOR.fullmatch(text):
        return text
    return ""


def _int_field(fields: dict[str, Desc], name: str, *, lo: int, hi: int) -> int | None:
    node = fields.get(name)
    if not isinstance(node, AtomDesc) or not node.has_value or node.type_name != "int":
        return None
    if isinstance(node.value, bool) or not isinstance(node.value, int):
        return None
    if node.value < lo or node.value > hi:
        return None
    return node.value


def _heading_level(raw) -> int:
    if raw in (None, "", 2, "2"):
        return 2
    if raw in (3, "3"):
        return 3
    raise InstantiationError("heading level must be 2 or 3")


def _theme_from(node: Desc) -> dict[str, str]:
    if not isinstance(node, StructDesc):
        return {}
    theme = dict(node.fields).get("theme")
    if not isinstance(theme, StructDesc):
        return {}
    fields = dict(theme.fields)
    out: dict[str, str] = {}
    mapping = (("background", "bg"), ("color", "fg"), ("accent", "accent"))
    for field, css in mapping:
        hex_value = _hex_color(_string_field(fields, field))
        if hex_value:
            out[css] = hex_value
    measure = _int_field(fields, "measure", lo=_MEASURE_MIN, hi=_MEASURE_MAX)
    if measure is not None:
        out["measure"] = f"{measure}rem"
    space = _int_field(fields, "space", lo=_SPACE_MIN, hi=_SPACE_MAX)
    if space is not None:
        out["space"] = f"{space}px"
    return out


def _merged_theme(root: Desc, page: Desc) -> dict[str, str]:
    merged = dict(_theme_from(root))
    merged.update(_theme_from(page))
    return merged


def _theme_style(theme: dict[str, str]) -> str:
    bits = []
    if theme.get("bg"):
        bits.append(f"--mp-bg:{theme['bg']}")
    if theme.get("fg"):
        bits.append(f"--mp-fg:{theme['fg']}")
    if theme.get("accent"):
        bits.append(f"--mp-accent:{theme['accent']}")
    if theme.get("measure"):
        bits.append(f"--mp-measure:{theme['measure']}")
    if theme.get("space"):
        bits.append(f"--mp-space:{theme['space']}")
    return ";".join(bits)


def _page_key(node: StructDesc) -> str:
    raw = _string_field(dict(node.fields), "key")
    if not raw:
        return ""
    try:
        return validate_slug(raw)
    except InstantiationError:
        return ""


def _internal_anchor(
    key: str,
    label: str,
    *,
    base: str,
    href_style: str,
    current: str = "",
) -> str:
    href = html.escape(page_href(base, key, href_style=href_style))
    extra = ""
    if href_style == HREF_PREVIEW:
        extra += f' data-mp-page="{html.escape(key)}"'
    if current and key == current:
        extra += ' aria-current="page"'
    return f'<a href="{href}"{extra}>{html.escape(label)}</a>'


def _render_nav(
    pages,
    base: str,
    current: str,
    *,
    href_style: str = HREF_HOST,
) -> str:
    links = []
    for item in pages:
        key, title = item[0], item[1]
        links.append(
            _internal_anchor(key, title or key, base=base, href_style=href_style, current=current)
        )
    return f'<nav class="mp-nav">{"".join(links)}</nav>'


def _render_document(
    node: StructDesc, *, base: str = "", href_style: str = HREF_HOST, asset_href=None
) -> str:
    body = dict(node.fields).get("body")
    if not isinstance(body, SequenceDesc):
        return ""
    chunks = [
        _render_block(item, base=base, href_style=href_style, asset_href=asset_href)
        for item in body.items
    ]
    return f'<div class="mp-body">{"".join(chunks)}</div>'


def _asset_url(name: str, *, base: str, href_style: str, asset_href) -> str:
    if asset_href is not None:
        custom = asset_href(name)
        if custom:
            return str(custom)
    if href_style == HREF_FILE:
        return name
    if href_style == HREF_PREVIEW:
        slug = base.rstrip("/").rsplit("/", 1)[-1]
        return f"/api/builder-core/meta/sites/{slug}/assets/{name}"
    return f"{base}/assets/{name}"


def _render_block(node: Desc, *, base: str = "", href_style: str = HREF_HOST, asset_href=None) -> str:
    if isinstance(node, AtomDesc) and node.has_value:
        return f"<p>{html.escape(str(node.value))}</p>"
    if isinstance(node, SequenceDesc):
        items = [
            f"<li>{html.escape(str(child.value))}</li>"
            for child in node.items
            if isinstance(child, AtomDesc) and child.has_value and str(child.value).strip()
        ]
        if items:
            return f'<ul class="mp-list">{"".join(items)}</ul>'
        return ""
    if isinstance(node, StructDesc):
        fields = dict(node.fields)
        heading = _string_field(fields, "heading")
        text = _string_field(fields, "text")
        target = _string_field(fields, "to")
        src = _string_field(fields, "src")
        quote = _string_field(fields, "quote")
        code = _string_field(fields, "code")
        if quote:
            return f"<blockquote>{html.escape(quote)}</blockquote>"
        if code:
            return f'<pre class="mp-code"><code>{html.escape(code)}</code></pre>'
        if src:
            try:
                name = validate_asset_name(src)
            except InstantiationError:
                name = ""
            if name:
                href = html.escape(_asset_url(name, base=base, href_style=href_style, asset_href=asset_href))
                return f'<p class="mp-img"><img src="{href}" alt="{html.escape(text)}"></p>'
        bits = []
        if heading:
            tag = "h3" if _int_field(fields, "level", lo=2, hi=3) == 3 else "h2"
            bits.append(f"<{tag}>{html.escape(heading)}</{tag}>")
        if text:
            bits.append(f"<p>{html.escape(text)}</p>")
        if target:
            try:
                key = validate_slug(target)
            except InstantiationError:
                key = ""
            if key:
                label = text or target
                return f"<p>{_internal_anchor(key, label, base=base, href_style=href_style)}</p>"
        if bits:
            return "".join(bits)
    return _render_desc(node)


def _event_form(action: str, event: str, csrf_token: str) -> str:
    token = html.escape(csrf_token)
    name = html.escape(event)
    href = html.escape(action)
    csrf = f'<input type="hidden" name="csrf_token" value="{token}">' if csrf_token else ""
    return (
        f'<form method="post" action="{href}">{csrf}'
        f'<input type="hidden" name="event" value="{name}">'
        f'<button type="submit">{name}</button></form>'
    )


def _render_desc(node: Desc) -> str:
    return f'<ul class="mp-tree">{_render_node(node)}</ul>'


def _render_node(node: Desc) -> str:
    if isinstance(node, AtomDesc):
        return f"<li>{_atom_text(node)}</li>"
    if isinstance(node, StructDesc):
        inner = "".join(
            f'<li><span class="mp-key">{html.escape(name)}</span> '
            f"<ul class=\"mp-tree\">{_render_node(child)}</ul></li>"
            for name, child in node.fields
        )
        return f"<li>struct<ul class=\"mp-tree\">{inner}</ul></li>"
    if isinstance(node, SequenceDesc):
        inner = "".join(_render_node(child) for child in node.items)
        return f"<li>sequence<ol class=\"mp-tree\">{inner}</ol></li>"
    if isinstance(node, MappingDesc):
        inner = "".join(
            f'<li><span class="mp-key">{html.escape(key)}</span> '
            f"<ul class=\"mp-tree\">{_render_node(child)}</ul></li>"
            for key, child in node.entries
        )
        return f"<li>mapping<ul class=\"mp-tree\">{inner}</ul></li>"
    return "<li>?</li>"


def _atom_text(node: AtomDesc) -> str:
    bits = [html.escape(node.type_name)]
    if node.has_value:
        bits.append(_value_text(node.type_name, node.value))
    if node.ref:
        bits.append(f"ref {html.escape(node.ref)}")
    if node.unit:
        bits.append(html.escape(node.unit))
    return " ".join(bits)


def _value_text(type_name: str, value: Any) -> str:
    if type_name == "bytes" and isinstance(value, (bytes, bytearray)):
        return f"({len(value)} bytes)"
    if type_name == "null" or value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return html.escape(str(value))
