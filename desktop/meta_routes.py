"""Desktop Application routes: compile meta descriptions onto local /build/<slug>."""

from __future__ import annotations

import html
import json

from flask import Response, abort, jsonify, redirect, request, send_file, stream_with_context

from desktop.meta_store import (
    MetaStoreError,
    application_asset_response,
    asset_data_url,
    current_draft_slug,
    delete_asset,
    delete_draft,
    delete_site,
    import_export_zip,
    list_artifacts,
    list_assets,
    list_drafts,
    load_draft,
    nested_cut_from_draft,
    load_layout,
    save_artifact,
    save_asset,
    save_draft,
    save_layout,
    search_all,
    studio_index,
    zip_app,
    zip_site,
)
from desktop.server_mode import desktop_enabled
from meta.description import equivalent, from_json, to_json
from meta.description.errors import DescriptionError
from meta.instantiation import InstantiationError, TARGET_DESKTOP_HOST, TARGET_DEVICE, TARGET_OS_HOST, TARGET_WEB_BUILD, add_site_page, add_system_part, apply_boundary_part_update, apply_page_part_theme, apply_page_part_update, apply_site_op, apply_step_at_key, apply_system_node_update, apply_system_part_op, boundary_copy, copy_surface, document_copy, duplicate_site_page, duplicate_system_part, instantiate, move_site_page, move_system_part, page_blocks, remove_site_page, remove_system_part, render_software_page, rename_site_page, root_system_title, set_system_title, site_pages, site_title, theme_copy, typed_local_key, update_page_copy, update_page_theme, update_site_title, validate_slug
from meta.instantiation.artifact import KNOWN_TARGETS
from meta.instantiation.page import HREF_PREVIEW
from meta.instantiation.system import flatten_system_pages, install_system_boundaries, locate_owning_part, part_artifact_at, part_at_path, part_home_key, resolve_system_part, system_parts
from meta.simulation import events_from_state, machine_from_desc, step
from meta.simulation.errors import SimulationError
from meta.boundary import BOUNDARY_KIND, META_SPACE_ID, boundary_from_desc, install_from_desc, list_boundaries as list_meta_boundaries, space_boundary_ids, space_desc as meta_space_desc
from meta.boundary.errors import BoundaryError
from meta.description.composite import StructDesc
from meta.description.types import AtomDesc
from meta.editor_views import list_views as list_editor_views
from meta.uir import desc_to_visual, from_desc, to_desc, uir_from_data, visual_to_desc
from meta.uir.errors import UIRError

_ASSET_UPLOAD_MAX = 256 * 1024


def _desc_from_body(body: dict):
    lang = str(body.get("language") or "json").strip().lower() or "json"
    if body.get("code"):
        from meta.uir import code_to_desc

        return code_to_desc(str(body.get("code") or ""), language=lang)
    if body.get("description") is not None:
        return from_json(json.dumps(body.get("description")))
    if body.get("visual") is not None:
        return visual_to_desc(body.get("visual"))
    if body.get("uir") is not None:
        return to_desc(uir_from_data(body.get("uir")))
    raise InstantiationError("code, description, visual, or uir required")


def _refresh_stamp_draft(pack: dict, *, data_root, prefer_slug: str = "") -> dict:
    from desktop.meta_store import MetaStoreError
    from meta.runtime.desktop_host import apply_desktop_host
    from plugin_catalog import PluginError, plugin_drafts, plugin_key_slug, project_from_packs, remember_plugin_draft, view_id_from_form

    root = data_root
    ident = str(pack.get("id") or "")
    mapped = plugin_drafts(root).get(ident)
    slug = str(prefer_slug or "").strip()
    if slug:
        try:
            load_draft(slug, base=root)
        except (MetaStoreError, InstantiationError):
            pass
    elif mapped:
        try:
            load_draft(mapped, base=root)
            slug = mapped
        except (MetaStoreError, InstantiationError):
            slug = ""
    if not slug:
        slug = plugin_key_slug(pack)
    document = pack.get("document")
    desc = None
    if document is not None:
        try:
            raw = document if isinstance(document, str) else json.dumps(document)
            desc = from_json(raw)
        except (DescriptionError, TypeError, ValueError):
            desc = None
    if desc is None:
        try:
            desc = project_from_packs([pack], title=str(pack.get("name") or ident or "plugin"))
        except PluginError:
            desc = None
    if desc is None:
        return {}
    code = to_json(desc, indent=2)
    dest = slug
    try:
        artifact = instantiate(desc, target=TARGET_DESKTOP_HOST, slug=slug)
        save_artifact(artifact)
        dest = artifact.slug or slug
        apply_desktop_host(
            desc,
            slug=dest,
            data_root=root,
            parts=artifact.payload_object().get("parts") if artifact.payload_object() else None,
        )
    except InstantiationError:
        dest = slug
    from desktop.meta_store import current_draft_slug

    stay = bool(prefer_slug) or current_draft_slug(base=root) in {dest, mapped}
    save_draft(dest, code=code, current=stay, base=root)
    remember_plugin_draft(root, ident, dest)
    from plugin_catalog import desc_fingerprint, record_stamp_timeline

    record_stamp_timeline(
        root,
        slug=dest,
        fingerprint=desc_fingerprint(code),
        pack_id=ident,
        document=code,
    )
    pane = str(pack.get("view") or "") or view_id_from_form(str(pack.get("form") or ""), str(pack.get("kindValue") or ""))
    studio = f"/studio/meta/{dest}" + (f"?pane={pane}" if pane else "")
    return {"code": code, "pane": pane or "code", "refreshed": True, "slug": dest, "studio": studio}


def _simulation_dict(desc) -> dict | None:
    try:
        machine = machine_from_desc(desc)
    except SimulationError:
        return None
    return {
        "events": list(events_from_state(machine)),
        "kind": "state_machine",
        "state": machine.state,
        "transitions": [
            {"event": item.event, "source": item.source, "target": item.target}
            for item in machine.transitions
        ],
    }


def _preview_dict(desc, slug: str | None = None, page_key: str | None = None) -> dict:
    try:
        install_from_desc(desc)
    except BoundaryError:
        pass
    try:
        install_system_boundaries(desc)
    except InstantiationError:
        pass
    visual = desc_to_visual(desc)
    restored = visual_to_desc(visual)
    uir = from_desc(desc).to_data()
    restored_uir = to_desc(uir_from_data(uir))
    payload = {
        "code": to_json(desc, indent=2),
        "yaml": "",
        "equivalent": bool(equivalent(desc, restored)),
        "equivalent_uir": bool(equivalent(desc, restored_uir)),
        "uir": uir,
        "visual": visual,
    }
    try:
        from meta.uir import to_code as emit_code

        payload["yaml"] = emit_code(desc, language="yaml")
    except UIRError:
        payload["yaml"] = ""
    sim_node = desc
    wanted_early = str(page_key or "").strip()
    found = resolve_system_part(desc, wanted_early or None)
    if found is not None:
        sim_node = found[2]
    simulation = _simulation_dict(sim_node)
    if simulation is None:
        simulation = _simulation_dict(desc)
    if simulation is not None:
        payload["simulation"] = simulation
    pages = [{"key": key, "title": title} for key, title, _page in site_pages(desc)]
    if not pages:
        try:
            pages = [
                {"key": key, "title": title}
                for key, title, _page in flatten_system_pages(desc)
            ]
        except InstantiationError:
            pages = []
    if pages:
        payload["pages"] = pages
    page_slug = "preview"
    try:
        if slug:
            page_slug = validate_slug(str(slug))
    except InstantiationError:
        page_slug = "preview"
    wanted = str(page_key or "").strip()
    if not wanted and pages:
        wanted = pages[0]["key"]
    if system_parts(desc):
        payload["kind"] = "meta.system"
        ident = ""
        if isinstance(desc, StructDesc):
            ident_node = dict(desc.fields).get("id")
            if isinstance(ident_node, AtomDesc) and ident_node.has_value and isinstance(ident_node.value, str):
                ident = ident_node.value
        if ident == META_SPACE_ID:
            payload["space"] = True
            payload["boundaries"] = list(space_boundary_ids())
        parts_doc = []
        for key, title, child in system_parts(desc):
            row = {"key": key, "kind": "", "title": title}
            if isinstance(child, StructDesc):
                kind_node = dict(child.fields).get("kind")
                if isinstance(kind_node, AtomDesc) and kind_node.has_value and isinstance(kind_node.value, str):
                    row["kind"] = kind_node.value
            if row["kind"] == BOUNDARY_KIND:
                try:
                    row["boundary"] = boundary_from_desc(child).to_data()
                except BoundaryError:
                    pass
            parts_doc.append(row)
        if parts_doc:
            payload["space_parts"] = parts_doc
        located = locate_owning_part(desc, wanted)
        if located is not None:
            path, part_key = located
            home = part_home_key(path, part_key)
            payload["part_key"] = home
            owner = desc if not path else part_at_path(desc, path)
            payload["can_remove_part"] = wanted == home and len(system_parts(owner)) > 1
            payload["can_move_part"] = len(system_parts(owner)) > 1
        label = root_system_title(desc)
        if label is not None:
            payload["system_title"] = label
    surface = copy_surface(desc, wanted or None)
    payload["copy_surface"] = surface
    payload["can_page_ops"] = surface in {"page", "site"}
    payload["can_theme"] = surface in {"page", "site"}
    copy = document_copy(desc, wanted or None)
    if copy is not None:
        payload["page_title"] = copy[0]
        payload["page_body"] = list(copy[1])
    bound = boundary_copy(desc, wanted or None)
    if bound is not None:
        payload["boundary"] = bound
    blocks = page_blocks(desc, wanted or None)
    if blocks is not None:
        payload["page_blocks"] = blocks
    theme = theme_copy(desc)
    if theme is not None:
        payload["page_theme"] = theme
    local_theme = theme_copy(desc, wanted or None, scope="page")
    if local_theme is not None:
        payload["page_theme_local"] = local_theme
    root_title = site_title(desc, wanted or None)
    if root_title is not None:
        payload["site_title"] = root_title
    try:
        payload["page_assets"] = list_assets(page_slug)
    except MetaStoreError:
        payload["page_assets"] = []
    try:
        artifact = instantiate(desc, slug=page_slug)

        def _preview_asset(name: str) -> str:
            return asset_data_url(page_slug, name)

        shown = artifact
        child = part_artifact_at(artifact, wanted or None)
        if child is not None:
            shown = child
        if shown.target != TARGET_WEB_BUILD:
            payload["page_html"] = _preview_artifact_html(shown)
        else:
            payload["page_html"] = render_software_page(
                artifact,
                page_key=wanted or None,
                href_style=HREF_PREVIEW,
                asset_href=_preview_asset,
            )
        payload["target"] = shown.target
        payload["page_slug"] = page_slug
        payload["page_key"] = wanted
        from meta.runtime.canvas import canvas_from_desc

        payload["canvas"] = canvas_from_desc(desc, page_key=wanted or None)
    except InstantiationError:
        pass
    return payload


def _preview_artifact_html(artifact) -> str:
    target = html.escape(artifact.target or "")
    bound = html.escape(artifact.boundary_id or "")
    body = html.escape(artifact.payload or "")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{target}</title></head>"
        f'<body class="mp-page" data-page-kind="{target}" data-boundary="{bound}">'
        f'<p class="mp-kicker">{target}</p>'
        f"<pre>{body}</pre></body></html>"
    )


def register_meta_routes(app, context) -> None:
    @app.context_processor
    def inject_local_meta():
        if not desktop_enabled():
            return {"current_draft_slug": None, "local_artifacts": [], "local_drafts": []}
        index = studio_index()
        return {
            "current_draft_slug": index["current"],
            "local_artifacts": index["artifacts"],
            "local_drafts": index["drafts"],
        }

    @app.get("/build/<slug>")
    def meta_build_root(slug: str):
        if not desktop_enabled():
            abort(404)
        from desktop.meta_store import load_artifact
        from meta.instantiation import description_from_artifact

        try:
            artifact = load_artifact(slug)
            rows = site_pages(description_from_artifact(artifact))
            if not rows:
                rows = flatten_system_pages(description_from_artifact(artifact))
        except (MetaStoreError, InstantiationError):
            abort(404)
        key = "home"
        if rows:
            keys = {item[0] for item in rows}
            key = "home" if "home" in keys else rows[0][0]
        return redirect(f"/build/{artifact.slug}/{key}")

    @app.get("/build/<slug>/assets/<name>")
    def meta_build_asset(slug: str, name: str):
        if not desktop_enabled():
            abort(404)
        page = application_asset_response(slug, name)
        if page is None:
            abort(404)
        return page

    @app.get("/api/builder-core/meta/sites/<slug>/assets/<name>")
    def meta_site_asset(slug: str, name: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        page = application_asset_response(slug, name)
        if page is None:
            abort(404)
        return page

    @app.post("/api/builder-core/meta/sites/<slug>/assets")
    def meta_site_asset_upload(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        upload = request.files.get("file")
        if upload is None:
            return jsonify({"error": "image required"}), 400
        raw = upload.read((_ASSET_UPLOAD_MAX) + 1)
        filename = str(upload.filename or request.form.get("name") or "")
        try:
            name = save_asset(slug, filename, raw)
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"name": name, "src": name, "assets": list_assets(slug)}), 201

    @app.get("/api/builder-core/meta/sites/<slug>/assets")
    def meta_site_assets(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        try:
            return jsonify({"assets": list_assets(slug)})
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/sites/<slug>/assets/remove")
    def meta_site_asset_remove(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        try:
            name = delete_asset(slug, str(body.get("name") or ""))
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"name": name, "assets": list_assets(slug)})

    @app.get("/api/builder-core/meta/index")
    def meta_studio_index():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        try:
            return jsonify(studio_index())
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/builder-core/meta/views")
    def meta_editor_views():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        surface = str(request.args.get("surface") or "").strip() or None
        from plugin_catalog import hardware_host_unlocked, unlocked_installs, view_unlocked

        from desktop.meta_store import data_dir

        rows = list_editor_views(surface)
        try:
            installed = unlocked_installs(data_dir())
        except MetaStoreError:
            installed = []
        return jsonify(
            {
                "views": [item for item in rows if view_unlocked(item["id"], installed)],
                "hardware": hardware_host_unlocked(installed),
            }
        )

    @app.get("/api/builder-core/meta/boundaries")
    def meta_boundaries():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        return jsonify({"boundaries": [item.to_data() for item in list_meta_boundaries()]})

    @app.get("/api/builder-core/meta/space")
    def meta_space():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        desc = meta_space_desc()
        return jsonify({
            "boundaries": list(space_boundary_ids()),
            "code": to_json(desc, indent=2),
            "id": "meta.space",
        })

    @app.post("/api/builder-core/meta/preview")
    def meta_preview():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        body = request.get_json(silent=True) or {}
        try:
            desc = _desc_from_body(body)
            return jsonify(_preview_dict(desc, str(body.get("slug") or ""), str(body.get("page_key") or "")))
        except (InstantiationError, DescriptionError, UIRError, json.JSONDecodeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/site-page")
    def meta_site_page():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        op = str(body.get("op") or "").strip()
        try:
            desc = _desc_from_body(body)
            current = str(body.get("page_key") or body.get("key") or "").strip()
            if op == "add":
                def _add(site, _local, _prefix):
                    updated = add_site_page(
                        site,
                        key=str(body.get("key") or "").strip() or None,
                        title=str(body.get("title") or ""),
                    )
                    return updated, site_pages(updated)[-1][0]

                desc, page_key = apply_site_op(desc, current, _add, promote=True)
            elif op == "remove":
                removed = str(body.get("key") or "").strip() or current

                def _remove(site, local, _prefix):
                    updated = remove_site_page(site, local)
                    keys = [item[0] for item in site_pages(updated)]
                    next_local = keys[0]
                    return updated, next_local

                desc, page_key = apply_site_op(desc, removed, _remove)
                keep = str(body.get("page_key") or "").strip()
                keys = {item[0] for item in site_pages(desc)}
                if not keys:
                    keys = {item[0] for item in flatten_system_pages(desc)}
                if keep and keep in keys:
                    page_key = keep
            elif op == "update":
                surface = copy_surface(desc, current)
                if surface == "page":
                    desc, page_key = apply_page_part_update(
                        desc,
                        current,
                        title=str(body.get("title") or ""),
                        body=None if isinstance(body.get("blocks"), list) else body.get("body"),
                        blocks=body.get("blocks") if isinstance(body.get("blocks"), list) else None,
                        new_key=str(body.get("new_key") or ""),
                    )
                elif surface == "boundary":
                    desc, page_key = apply_boundary_part_update(
                        desc,
                        current,
                        title=str(body.get("title") or ""),
                        new_key=str(body.get("new_key") or ""),
                        bound_id=str(body.get("boundary_id") or ""),
                        surface_kind=str(body.get("surface") or ""),
                        target=str(body.get("target") or ""),
                        meta_level=body.get("meta_level"),
                    )
                elif surface == "system":
                    desc, page_key = apply_system_node_update(
                        desc,
                        current,
                        title=str(body.get("title") or ""),
                        new_key=str(body.get("new_key") or ""),
                    )
                elif surface == "site":
                    def _update(site, local, prefix):
                        updated = site
                        site_name = str(body.get("site_title") or "").strip()
                        if site_name:
                            updated = update_site_title(updated, site_name)
                        new_key = typed_local_key(str(body.get("new_key") or ""), local, prefix)
                        if new_key and new_key != local:
                            updated = rename_site_page(updated, local, new_key)
                            local = new_key
                        blocks = body.get("blocks") if isinstance(body.get("blocks"), list) else None
                        updated = update_page_copy(
                            updated,
                            key=local or None,
                            title=str(body.get("title") or ""),
                            body=None if blocks is not None else body.get("body"),
                            blocks=blocks,
                        )
                        keys = {item[0] for item in site_pages(updated)}
                        if local not in keys:
                            local = site_pages(updated)[0][0]
                        return updated, local

                    desc, page_key = apply_site_op(desc, current, _update)
                else:
                    raise InstantiationError("update requires software.page, software.site, meta.boundary, or meta.system")
                sys_label = str(body.get("system_title") or "").strip()
                if sys_label and root_system_title(desc) is not None:
                    desc = set_system_title(desc, sys_label)
            elif op == "move":
                try:
                    delta = int(body.get("delta"))
                except (TypeError, ValueError):
                    return jsonify({"error": "delta must be -1 or 1"}), 400

                def _move(site, local, _prefix):
                    return move_site_page(site, local, delta=delta), local

                desc, page_key = apply_site_op(desc, current, _move, promote=True)
            elif op == "duplicate":
                source = str(body.get("key") or body.get("page_key") or "").strip()

                def _duplicate(site, local, _prefix):
                    updated = duplicate_site_page(site, local)
                    keys = [item[0] for item in site_pages(updated)]
                    next_local = keys[-1]
                    try:
                        next_local = keys[keys.index(local) + 1]
                    except (ValueError, IndexError):
                        pass
                    return updated, next_local

                desc, page_key = apply_site_op(desc, source or current, _duplicate, promote=True)
            elif op == "theme":
                surface = copy_surface(desc, current)
                if surface == "page":
                    desc, page_key = apply_page_part_theme(
                        desc,
                        current,
                        body.get("theme") if isinstance(body.get("theme"), dict) else {},
                        scope=str(body.get("scope") or "site"),
                    )
                elif surface == "site":
                    def _theme(site, local, _prefix):
                        updated = update_page_theme(
                            site,
                            body.get("theme") if isinstance(body.get("theme"), dict) else {},
                            key=local or None,
                            scope=str(body.get("scope") or "site"),
                        )
                        keys = {item[0] for item in site_pages(updated)}
                        if local not in keys:
                            local = site_pages(updated)[0][0]
                        return updated, local

                    desc, page_key = apply_site_op(desc, current, _theme)
                else:
                    raise InstantiationError("theme requires software.page or software.site")
            else:
                return jsonify({"error": "op must be add, remove, update, move, duplicate, or theme"}), 400
            return jsonify(_preview_dict(desc, str(body.get("slug") or ""), page_key))
        except (InstantiationError, DescriptionError, UIRError, json.JSONDecodeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/system-part")
    def meta_system_part():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        op = str(body.get("op") or "").strip()
        try:
            desc = _desc_from_body(body)
            current = str(body.get("page_key") or body.get("key") or "").strip()
            if op == "add":
                def _add(system, _part_key):
                    updated = add_system_part(
                        system,
                        key=str(body.get("key") or "").strip() or None,
                        title=str(body.get("title") or ""),
                        part_kind=str(body.get("kind") or "").strip() or None,
                    )
                    return updated, system_parts(updated)[-1][0]

                desc, page_key = apply_system_part_op(desc, current, _add)
            elif op == "remove":
                located = locate_owning_part(desc, current)
                if located is None:
                    raise InstantiationError("unknown system part")
                path, part_key = located
                home = part_home_key(path, part_key)
                if current and current != home:
                    raise InstantiationError("remove part from the part home")

                def _remove(system, local):
                    updated = remove_system_part(system, local)
                    return updated, system_parts(updated)[0][0]

                desc, page_key = apply_system_part_op(desc, current, _remove)
                keep = str(body.get("page_key") or "").strip()
                keys = {item[0] for item in flatten_system_pages(desc)}
                if keep and keep in keys:
                    page_key = keep
            elif op == "move":
                try:
                    delta = int(body.get("delta"))
                except (TypeError, ValueError):
                    return jsonify({"error": "delta must be -1 or 1"}), 400

                def _move(system, local):
                    return move_system_part(system, local, delta=delta), local

                desc, page_key = apply_system_part_op(desc, current, _move)
            elif op == "duplicate":
                def _duplicate(system, local):
                    updated = duplicate_system_part(system, local)
                    keys = [item[0] for item in system_parts(updated)]
                    next_local = keys[-1]
                    try:
                        next_local = keys[keys.index(local) + 1]
                    except (ValueError, IndexError):
                        pass
                    return updated, next_local

                desc, page_key = apply_system_part_op(desc, current, _duplicate)
            else:
                return jsonify({"error": "op must be add, remove, move, or duplicate"}), 400
            return jsonify(_preview_dict(desc, str(body.get("slug") or ""), page_key))
        except (InstantiationError, DescriptionError, UIRError, json.JSONDecodeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/step")
    def meta_step():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        try:
            desc = _desc_from_body(body)
            desc, page_key = apply_step_at_key(
                desc,
                str(body.get("page_key") or ""),
                str(body.get("event") or ""),
            )
            payload = _preview_dict(
                desc,
                str(body.get("slug") or ""),
                page_key,
            )
            return jsonify(payload)
        except (InstantiationError, DescriptionError, UIRError, SimulationError, json.JSONDecodeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/instantiate")
    def meta_instantiate():
        if not desktop_enabled():
            abort(404)
        context("builder.publish")
        body = request.get_json(silent=True) or {}
        slug = str(body.get("slug") or "").strip()
        events = body.get("events") or ()
        if events is not None and not isinstance(events, (list, tuple)):
            return jsonify({"error": "events must be a list"}), 400
        try:
            source = _desc_from_body(body)
            try:
                machine = machine_from_desc(source)
                source = machine
            except SimulationError:
                pass
            wanted = str(body.get("target") or "").strip()
            if wanted and wanted not in KNOWN_TARGETS:
                raise InstantiationError(f"unsupported target: {wanted!r}")
            artifact = instantiate(
                source,
                target=wanted or None,
                slug=slug,
                events=list(events) if events else None,
            )
            save_artifact(artifact)
        except (InstantiationError, DescriptionError, MetaStoreError, BoundaryError, UIRError) as exc:
            return jsonify({"error": str(exc)}), 400
        body = {
            "checksum": artifact.checksum,
            "public_url": artifact.public_url,
            "slug": artifact.slug,
            "target": artifact.target,
        }
        if artifact.target == TARGET_WEB_BUILD and artifact.slug:
            body["zip_url"] = f"/api/builder-core/meta/sites/{artifact.slug}/zip"
            body["studio"] = f"/studio/meta/{artifact.slug}"
        from meta.runtime.canvas import canvas_from_artifact

        try:
            body["canvas"] = canvas_from_artifact(artifact)
        except InstantiationError:
            body["canvas"] = None
        if artifact.target == TARGET_DEVICE:
            from desktop.meta_store import data_dir
            from meta.runtime.hardware import persist_device_artifact

            persist_device_artifact(artifact.payload_object(), data_root=data_dir())
            body["device"] = artifact.payload_object().get("device")
            body["esphome"] = artifact.payload_object().get("esphome")
        if artifact.target == TARGET_OS_HOST:
            from desktop.meta_store import data_dir
            from meta.runtime.os_surface import apply_host
            from meta.instantiation import description_from_artifact

            body["host"] = apply_host(
                description_from_artifact(artifact),
                slug=artifact.slug or slug,
                data_root=data_dir(),
            )["host"]
        if artifact.target == TARGET_DESKTOP_HOST:
            from desktop.meta_store import data_dir
            from meta.runtime.desktop_host import apply_desktop_host
            from meta.instantiation import description_from_artifact

            stored = apply_desktop_host(
                description_from_artifact(artifact),
                slug=artifact.slug or slug,
                data_root=data_dir(),
                parts=artifact.payload_object().get("parts") if artifact.payload_object() else None,
            )
            body["host"] = stored["host"]
            body["studio"] = stored["studio"]
            body["self"] = stored["self"]
        return jsonify(body), 201

    @app.post("/api/builder-core/meta/produce")
    def meta_produce():
        if not desktop_enabled():
            abort(404)
        context("builder.publish")
        body = request.get_json(silent=True) or {}
        slug = str(body.get("slug") or "made").strip() or "made"
        try:
            from meta.runtime.produce import guess_kind, produce
            from plugin_catalog import PluginError, stamp_plugin

            prompt = str(body.get("prompt") or "")
            kind = str(body.get("kind") or "")
            title = str(body.get("title") or "")
            if guess_kind(prompt, kind) == "plugin":
                from desktop.meta_store import data_dir

                cycle = stamp_plugin(
                    name=title or prompt or "plugin",
                    form=str(body.get("form") or prompt or ""),
                    document=body.get("document") if body.get("document") is not None else body.get("code"),
                    data_root=data_dir(),
                )
                return jsonify(
                    {
                        "kind": "plugin",
                        "loop": cycle["loop"],
                        "model": False,
                        "openai": False,
                        "pack": cycle["pack"],
                        "path": cycle.get("path"),
                    }
                ), 201
            made = produce(
                prompt=prompt,
                kind=kind,
                title=title,
                slug=slug,
                target=str(body.get("target") or "") or None,
            )
            artifact = made["artifact"]
            save_artifact(artifact)
        except (InstantiationError, DescriptionError, MetaStoreError, BoundaryError, UIRError, PluginError) as exc:
            return jsonify({"error": str(exc), "model": False, "openai": False}), 400
        out = {
            "checksum": artifact.checksum,
            "code": made["code"],
            "kind": made["kind"],
            "model": False,
            "openai": False,
            "public_url": artifact.public_url,
            "slug": artifact.slug,
            "target": artifact.target,
        }
        if artifact.target == TARGET_WEB_BUILD and artifact.slug:
            save_draft(artifact.slug, code=made["code"] or "")
            out["zip_url"] = f"/api/builder-core/meta/sites/{artifact.slug}/zip"
            out["studio"] = f"/studio/meta/{artifact.slug}"
        if artifact.target == TARGET_DESKTOP_HOST:
            from desktop.meta_store import data_dir
            from meta.runtime.desktop_host import apply_desktop_host
            from meta.instantiation import description_from_artifact

            stored = apply_desktop_host(
                description_from_artifact(artifact),
                slug=artifact.slug or slug,
                data_root=data_dir(),
                parts=artifact.payload_object().get("parts") if artifact.payload_object() else None,
            )
            out["host"] = stored["host"]
            out["studio"] = stored["studio"]
            if artifact.slug:
                out["zip_url"] = f"/api/builder-core/meta/apps/{artifact.slug}/zip"
        return jsonify(out), 201

    @app.post("/api/builder-core/meta/page/<slug>/step")
    def meta_page_step(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        event = request.form.get("event") or body.get("event") or ""
        from desktop.meta_store import load_artifact
        from meta.instantiation import description_from_artifact

        try:
            current = load_artifact(slug)
            desc = description_from_artifact(current)
            advanced = step(machine_from_desc(desc), str(event))
            artifact = instantiate(advanced, target=current.target, slug=slug)
            save_artifact(artifact)
        except (InstantiationError, DescriptionError, MetaStoreError, SimulationError) as exc:
            if request.is_json or request.headers.get("Content-Type", "").startswith("application/json"):
                return jsonify({"error": str(exc)}), 400
            abort(400)
        state = machine_from_desc(description_from_artifact(artifact)).state
        wants_json = (
            request.is_json
            or request.headers.get("Accept", "").startswith("application/json")
            or request.headers.get("Content-Type", "").startswith("application/json")
        )
        if wants_json or artifact.target != TARGET_WEB_BUILD:
            return jsonify({
                "public_url": artifact.public_url,
                "slug": artifact.slug,
                "state": state,
                "target": artifact.target,
            })
        return redirect(f"/build/{artifact.slug}/home")

    @app.get("/api/builder-core/meta/artifacts")
    def meta_artifacts():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        try:
            rows = list_artifacts()
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"artifacts": rows})

    @app.get("/api/builder-core/meta/artifacts/<slug>")
    def meta_artifact(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from desktop.meta_store import load_artifact

        try:
            artifact = load_artifact(slug)
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(artifact.to_data())

    @app.get("/api/builder-core/meta/sites/<slug>/zip")
    def meta_site_zip(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        import io

        try:
            payload = zip_site(slug)
        except (InstantiationError, MetaStoreError):
            abort(404)
        buf = io.BytesIO(payload)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{slug}.zip",
        )

    @app.get("/api/builder-core/meta/apps/<slug>/zip")
    def meta_app_zip(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        import io

        try:
            payload = zip_app(slug)
        except (InstantiationError, MetaStoreError):
            abort(404)
        buf = io.BytesIO(payload)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{slug}.zintriq-app.zip",
        )

    @app.post("/api/builder-core/meta/sites/import")
    def meta_site_import():
        if not desktop_enabled():
            abort(404)
        context("builder.publish")
        upload = request.files.get("site")
        if upload is None:
            return jsonify({"error": "site zip required"}), 400
        raw = upload.read((4 * 1024 * 1024) + 1)
        try:
            body = import_export_zip(raw, slug=request.form.get("slug") or None)
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(body), 201

    @app.post("/api/builder-core/meta/sites/<slug>/remove")
    def meta_site_remove(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.publish")
        try:
            deleted = delete_site(slug)
        except InstantiationError:
            abort(404)
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify({"slug": deleted})

    @app.post("/api/builder-core/meta/drafts")
    def meta_save_draft():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        try:
            payload = save_draft(
                str(body.get("slug") or ""),
                code=str(body.get("code") or ""),
                events=str(body.get("events") or ""),
            )
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(payload)

    @app.get("/api/builder-core/meta/drafts")
    def meta_list_drafts():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        try:
            return jsonify({"current": current_draft_slug(), "drafts": list_drafts()})
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/drafts/remove")
    def meta_draft_remove():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        try:
            deleted = delete_draft(str(body.get("slug") or ""))
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify({"slug": deleted})

    @app.post("/api/builder-core/meta/drafts/rename")
    def meta_draft_rename():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from desktop.meta_store import DraftSlugTaken, rename_draft

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                rename_draft(str(body.get("slug") or body.get("from") or ""), str(body.get("to") or body.get("name") or ""))
            )
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        except DraftSlugTaken as exc:
            return jsonify(
                {
                    "conflict_chain": list(exc.conflict_chain or []),
                    "error": str(exc),
                    "free_slots": list(exc.free_slots or []),
                    "suggestion": exc.suggestion,
                }
            ), 409
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/drafts/fill")
    def meta_draft_fill():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from desktop.meta_store import fill_draft_skeleton

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                fill_draft_skeleton(
                    str(body.get("slug") or ""),
                    pack_id=str(body.get("id") or body.get("pack_id") or "official-scene"),
                )
            )
        except InstantiationError:
            return jsonify({"error": "invalid slug"}), 400
        except MetaStoreError as exc:
            msg = str(exc)
            payload = {"error": msg}
            if "community" in msg.lower() or "install a view pack" in msg.lower():
                payload["community"] = "/app/community"
                payload["hint"] = "No installed main view. Install a pack (e.g. UI or Scene), then Fill."
                payload["suggest_pack"] = "official-ui"
            return jsonify(payload), 400

    @app.get("/api/builder-core/meta/drafts/<slug>")
    def meta_get_draft(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        try:
            return jsonify(load_draft(slug))
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/builder-core/meta/drafts/<slug>/cut")
    def meta_get_draft_cut(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        try:
            return jsonify({"slug": slug, "shots": nested_cut_from_draft(slug)})
        except InstantiationError:
            return jsonify({"error": "invalid slug", "shots": []}), 400
        except MetaStoreError as exc:
            return jsonify({"error": str(exc), "shots": []}), 404

    @app.get("/api/builder-core/meta/hardware")
    def meta_hardware_list():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from desktop.meta_store import data_dir
        from meta.runtime.hardware import list_devices

        return jsonify({"devices": list_devices(data_dir())})

    @app.post("/api/builder-core/meta/hardware/pair")
    def meta_hardware_pair():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        from desktop.meta_store import data_dir
        from meta.runtime.hardware import esphome_yaml, flash_plan, pair

        try:
            desc = _desc_from_body(body)
            device = pair(desc, port=str(body.get("port") or "usb"), data_root=data_dir())
            yaml_text = esphome_yaml(desc, device)
            plan = flash_plan(device, yaml_text, data_root=data_dir())
        except (InstantiationError, DescriptionError, json.JSONDecodeError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"device": device.to_data(), "flash": plan, "esphome": yaml_text}), 201

    @app.post("/api/builder-core/meta/os/apply")
    def meta_os_apply():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        from desktop.meta_store import data_dir
        from meta.runtime.os_surface import apply_host

        try:
            desc = _desc_from_body(body)
            payload = apply_host(desc, slug=str(body.get("slug") or "host"), data_root=data_dir())
        except (InstantiationError, DescriptionError, json.JSONDecodeError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(payload), 201

    @app.get("/api/builder-core/meta/collab/<slug>")
    def meta_collab_get(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from desktop.meta_store import data_dir
        from meta.collab.store import load
        from meta.collab import to_plain
        from meta.instantiation import validate_slug as _slug

        try:
            clean = _slug(slug)
            state = load(data_dir(), clean)
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        code = None
        if state.get("doc") is not None:
            code = json.dumps(to_plain(state["doc"]), ensure_ascii=False, indent=2)
        return jsonify(
            {
                "clock": state.get("clock"),
                "code": code,
                "doc": state.get("doc"),
                "replica": state.get("replica"),
            }
        )

    @app.post("/api/builder-core/meta/collab")
    def meta_collab_push():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        from desktop.meta_store import data_dir
        from meta.collab.store import push_plain
        from meta.description.serialize import to_data

        try:
            clean = validate_slug(str(body.get("slug") or ""))
            desc = _desc_from_body(body)
            state = push_plain(data_dir(), clean, to_data(desc))
        except (InstantiationError, DescriptionError, UIRError, json.JSONDecodeError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(
            {
                "clock": state.get("clock"),
                "code": json.dumps(state.get("plain"), ensure_ascii=False, indent=2),
                "replica": state.get("replica"),
            }
        )

    @app.post("/api/builder-core/meta/collab/merge")
    def meta_collab_merge():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        from desktop.meta_store import data_dir
        from meta.collab.store import pull_merged

        try:
            clean = validate_slug(str(body.get("slug") or ""))
            state = pull_merged(
                data_dir(),
                clean,
                {"clock": body.get("clock") or {}, "doc": body.get("doc")},
            )
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        code = None
        if state.get("plain") is not None:
            code = json.dumps(state["plain"], ensure_ascii=False, indent=2)
        return jsonify({"clock": state.get("clock"), "code": code, "doc": state.get("doc"), "replica": state.get("replica")})

    @app.post("/api/builder-core/meta/collab/join")
    def meta_collab_join():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        from desktop.meta_store import data_dir
        from meta.collab.store import join_room, push_replica, room_state

        try:
            clean = validate_slug(str(body.get("slug") or ""))
            room = join_room(data_dir(), clean, str(body.get("replica") or ""))
            if body.get("code") or body.get("description"):
                desc = _desc_from_body(body)
                from meta.description.serialize import to_data

                pushed = push_replica(data_dir(), clean, room["replica"], to_data(desc))
                room["clock"] = pushed.get("clock")
                room["code"] = json.dumps(pushed.get("plain"), ensure_ascii=False, indent=2)
            else:
                state = room_state(data_dir(), clean)
                room["clock"] = state.get("clock")
                if state.get("plain") is not None:
                    room["code"] = json.dumps(state["plain"], ensure_ascii=False, indent=2)
        except (InstantiationError, DescriptionError, UIRError, json.JSONDecodeError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(room)

    @app.post("/api/builder-core/meta/collab/sync")
    def meta_collab_sync():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        from desktop.meta_store import data_dir
        from meta.collab.store import sync_mailbox

        try:
            clean = validate_slug(str(body.get("slug") or ""))
            state = sync_mailbox(data_dir(), clean)
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        code = json.dumps(state.get("plain"), ensure_ascii=False, indent=2) if state.get("plain") is not None else None
        return jsonify({"code": code, "peers": state.get("peers"), "replica": state.get("replica"), "slug": clean})

    @app.get("/api/builder-core/meta/collab/room/<slug>")
    def meta_collab_room(slug: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from desktop.meta_store import data_dir
        from meta.collab.store import room_state
        from meta.instantiation import validate_slug as _slug

        try:
            return jsonify(room_state(data_dir(), _slug(slug)))
        except (InstantiationError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/builder-core/meta/hardware/ports")
    def meta_hardware_ports():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from desktop.meta_store import data_dir
        from meta.runtime.hardware import list_serial_ports, wifi_public

        return jsonify({"ports": list_serial_ports(), "wifi": wifi_public(data_dir())})

    @app.get("/api/builder-core/meta/hardware/buses")
    def meta_hardware_buses():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from meta.runtime.buses import list_all

        return jsonify({"buses": list_all()})

    @app.post("/api/builder-core/meta/hardware/buses/transfer")
    def meta_hardware_bus_xfer():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from meta.runtime.buses import BusError, transfer

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(transfer(str(body.get("kind") or ""), str(body.get("device") or ""), str(body.get("payload") or "")))
        except BusError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/hardware/buses/session")
    def meta_hardware_bus_open():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from meta.runtime.buses import BusError, open_session

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(open_session(str(body.get("kind") or ""), str(body.get("device") or "")))
        except BusError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/hardware/buses/session/write")
    def meta_hardware_bus_write():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from meta.runtime.buses import BusError, session_write

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(session_write(str(body.get("session") or ""), str(body.get("payload") or "")))
        except BusError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/hardware/buses/session/read")
    def meta_hardware_bus_read():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from meta.runtime.buses import BusError, session_read

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(session_read(str(body.get("session") or ""), int(body.get("n") or 256)))
        except BusError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/hardware/buses/session/close")
    def meta_hardware_bus_close():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from meta.runtime.buses import BusError, close_session

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(close_session(str(body.get("session") or "")))
        except BusError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/hardware/flash")
    def meta_hardware_flash():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        from desktop.meta_store import data_dir
        from meta.runtime.hardware import esphome_yaml, flash_plan, pair, start_flash

        try:
            yaml_path = str(body.get("yaml_path") or "").strip()
            port = str(body.get("port") or "").strip()
            if not yaml_path:
                desc = _desc_from_body(body)
                device = pair(desc, port=port or "usb", data_root=data_dir())
                yaml_text = esphome_yaml(desc, device)
                plan = flash_plan(device, yaml_text, data_root=data_dir())
                yaml_path = plan["yaml_path"]
                if not port:
                    port = device.port
            job = start_flash(
                port=port,
                yaml_path=yaml_path,
                data_root=data_dir(),
                ssid=str(body.get("wifi_ssid") or "").strip() or None,
                password=body.get("wifi_password") if "wifi_password" in body else None,
            )
        except (InstantiationError, DescriptionError, UIRError, json.JSONDecodeError, MetaStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(job), 202

    @app.get("/api/builder-core/meta/hardware/jobs/<job_id>")
    def meta_hardware_job(job_id: str):
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from meta.runtime.hardware import job_status

        row = job_status(job_id)
        if row is None:
            return jsonify({"error": "unknown job"}), 404
        return jsonify(row)

    @app.get("/api/builder-core/meta/search")
    def meta_search():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        q = str(request.args.get("q") or "")
        if str(request.args.get("sql") or "").strip():
            return jsonify({"error": "arbitrary SQL is not allowed"}), 400
        try:
            return jsonify(
                {
                    "hits": search_all(
                        q,
                        form=str(request.args.get("form") or ""),
                        kind=str(request.args.get("kind") or ""),
                        fingerprint=str(request.args.get("fingerprint") or ""),
                        stamped=str(request.args.get("stamped") or ""),
                        meta_level=str(request.args.get("meta_level") or ""),
                        meta_level_min=str(request.args.get("meta_level_min") or ""),
                        meta_level_max=str(request.args.get("meta_level_max") or ""),
                    )
                }
            )
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/builder-core/meta/layout")
    def meta_layout_get():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        try:
            return jsonify(load_layout())
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/layout")
    def meta_layout_post():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        if body.get("op") == "split":
            from desktop.layout import split_group

            return jsonify(save_layout(split_group(load_layout(), direction=str(body.get("direction") or "right"))))
        if body.get("op") == "pin":
            from desktop.layout import pin_editor

            return jsonify(save_layout(pin_editor(load_layout(), str(body.get("id") or ""))))
        if body.get("op") == "chrome":
            from desktop.layout import set_chrome

            return jsonify(
                save_layout(
                    set_chrome(
                        load_layout(),
                        sidebar=body.get("sidebar"),
                        panel=body.get("panel"),
                        zen=body.get("zen"),
                        activity=body.get("activity"),
                        panel_tab=body.get("panelTab"),
                        columns=body.get("columns"),
                    )
                )
            )
        if body.get("op") == "profile":
            from desktop.layout import apply_profile, save_profile

            layout = load_layout()
            name = str(body.get("name") or "default")
            if body.get("apply"):
                layout = apply_profile(layout, name)
            else:
                layout = save_profile(layout, name)
            return jsonify(save_layout(layout))
        if body.get("op") == "mru":
            from desktop.layout import remember_editor

            return jsonify(save_layout(remember_editor(load_layout(), str(body.get("id") or ""))))
        if body.get("op") == "stick":
            from desktop.layout import stick_editor

            return jsonify(save_layout(stick_editor(load_layout(), str(body.get("id") or ""))))
        if body.get("op") == "reset":
            from desktop.layout import reset_layout

            return jsonify(save_layout(reset_layout(load_layout())))
        if body.get("op") == "tab":
            from desktop.layout import close_tab

            return jsonify(save_layout(close_tab(load_layout(), str(body.get("id") or ""))))
        if body.get("op") == "max":
            from desktop.layout import maximize_editor

            return jsonify(save_layout(maximize_editor(load_layout(), str(body.get("id") or ""))))
        if body.get("op") == "cycle":
            from desktop.layout import cycle_mru

            return jsonify(save_layout(cycle_mru(load_layout(), offset=int(body.get("offset") or 1))))
        if body.get("op") == "focus":
            from desktop.layout import focus_editor, focus_group

            if body.get("group") is not None:
                return jsonify(save_layout(focus_group(load_layout(), int(body.get("group") or 0))))
            return jsonify(save_layout(focus_editor(load_layout(), str(body.get("id") or ""))))
        if body.get("op") == "swap":
            from desktop.layout import swap_groups

            return jsonify(save_layout(swap_groups(load_layout(), int(body.get("a") or 0), int(body.get("b") or 1))))
        try:
            return jsonify(save_layout(body if isinstance(body, dict) else {}))
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/query")
    def meta_query():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from meta.query import QueryError, visual_query

        body = request.get_json(silent=True) or {}
        rows = body.get("rows")
        spec = body.get("query")
        if not isinstance(rows, list):
            return jsonify({"error": "rows required"}), 400
        try:
            return jsonify({"rows": visual_query(rows, spec if isinstance(spec, dict) else None)})
        except QueryError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/connectors/allow")
    def meta_connector_allow():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from meta.runtime.connectors import ConnectorError, allow

        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"url": allow(str(body.get("url") or ""))})
        except ConnectorError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/plugin")
    @app.get("/api/builder-core/meta/plugins")
    def meta_plugins():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from plugin_catalog import catalog, installed_index

        from desktop.meta_store import data_dir

        have = set(installed_index(data_dir()))
        from plugin_catalog import desc_fingerprint, pack_view_id, plugin_drafts, stamp_timeline
        from desktop.meta_store import load_draft

        drafts = plugin_drafts(data_dir())
        packs = []
        for row in catalog(include_pending=True, data_root=data_dir()):
            item = dict(row)
            ident = str(item.get("id") or "")
            item["installed"] = ident in have
            item["view"] = pack_view_id(item)
            bound = drafts.get(ident) or ""
            item["draft_slug"] = bound
            item["draft_updated_at"] = ""
            item["draft_matches"] = False
            if bound:
                try:
                    draft = load_draft(bound, base=data_dir())
                    item["draft_updated_at"] = str(draft.get("updated_at") or "")
                    item["draft_matches"] = desc_fingerprint(draft.get("code")) == desc_fingerprint(item.get("document"))
                except (MetaStoreError, InstantiationError):
                    pass
            packs.append(item)
        slug = str(request.args.get("slug") or "")
        return jsonify(
            {
                "installed": sorted(have),
                "packs": packs,
                "timeline": stamp_timeline(data_dir(), slug),
            }
        )

    @app.get("/api/plugin/installed")
    @app.get("/api/builder-core/meta/plugins/installed")
    def meta_plugin_installed():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from plugin_catalog import installed_index

        from desktop.meta_store import data_dir

        return jsonify({"installed": installed_index(data_dir())})

    @app.post("/api/plugin/stamp")
    @app.post("/api/builder-core/meta/plugins/stamp")
    def meta_plugin_stamp():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import PluginError, stamp_plugin

        from desktop.meta_store import data_dir

        body = request.get_json(silent=True) or {}
        try:
            cycle = stamp_plugin(
                name=str(body.get("name") or body.get("title") or ""),
                form=str(body.get("form") or ""),
                summary=str(body.get("summary") or ""),
                kind=str(body.get("kind") or body.get("kindValue") or ""),
                document=body.get("document") if body.get("document") is not None else body.get("code"),
                data_root=data_dir(),
                pack_id=str(body.get("id") or body.get("pack_id") or ""),
                draft_slug=str(body.get("slug") or ""),
            )
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400
        pack = cycle.get("pack") or {}
        prefer = str(body.get("slug") or "")
        if not prefer:
            from plugin_catalog import plugin_drafts

            prefer = plugin_drafts(data_dir()).get(str(pack.get("id") or "")) or ""
        if prefer and pack.get("id"):
            from plugin_catalog import remember_plugin_draft

            remember_plugin_draft(data_dir(), str(pack.get("id") or ""), prefer)
        try:
            cycle.update(_refresh_stamp_draft(pack, data_root=data_dir(), prefer_slug=prefer))
        except (DescriptionError, InstantiationError, MetaStoreError):
            pass
        return jsonify(cycle), 201

    @app.post("/api/plugin/install")
    @app.post("/api/builder-core/meta/plugins/install")
    def meta_plugin_install():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from desktop.meta_store import data_dir, index_upsert

        body = request.get_json(silent=True) or {}
        ident = str(body.get("id") or "").strip()
        from plugin_catalog import (
            PluginError,
            catalog,
            installable,
            official_pack_file,
            record_install,
            review,
            submit,
            validate_manifest,
            verify_pack,
            verify_pack_digest,
            view_id_from_form,
        )

        pack = next((row for row in catalog(include_pending=True) if row["id"] == ident), None)
        if pack is None and body.get("manifest"):
            try:
                pack = submit(body.get("manifest") or {})
                if pack.get("stamp"):
                    review(pack["id"], "approved")
                    pack = dict(pack)
                    pack["status"] = "approved"
            except PluginError as exc:
                return jsonify({"error": str(exc)}), 400
        if not pack:
            return jsonify({"error": "unknown pack"}), 404
        if not installable(pack):
            return jsonify({"error": "pack is not approved"}), 403
        fname = str(pack.get("file") or "")
        full = official_pack_file(fname) if fname else None
        if full:
            pack = full
            ident = str(pack.get("id") or ident)
        try:
            validate_manifest(pack)
            verify_pack(pack, required=bool(pack.get("signature")) or str(pack.get("origin") or "") == "remote")
            verify_pack_digest(pack, required=bool(full) or bool(pack.get("sha256")))
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400
        folder = data_dir() / "plugins"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / pack["file"]
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        index_upsert("plugin", ident, json.dumps(pack), base=data_dir())
        record_install(data_dir(), ident)
        view = str(pack.get("view") or "") or view_id_from_form(str(pack.get("form") or ""), str(pack.get("kindValue") or ident.replace("official-", "")))
        from desktop.meta_store import current_draft_slug

        payload = {
            "draft": current_draft_slug() or "",
            "home": "/studio",
            "id": ident,
            "installed": True,
            "loop": "plugin-project-plugin",
            "path": str(path),
            "sandbox": bool(pack.get("sandbox")),
            "pane": view or "code",
        }
        if pack.get("stamp"):
            current = str(payload.get("draft") or "")
            from plugin_catalog import plugin_drafts

            mapped = plugin_drafts(data_dir()).get(ident) or ""
            if not current or current == mapped:
                try:
                    payload.update(_refresh_stamp_draft(pack, data_root=data_dir(), prefer_slug=mapped))
                except (DescriptionError, InstantiationError, MetaStoreError):
                    pass
            payload["draft"] = current or str(payload.get("draft") or "")
            payload["home"] = "/studio"
        return jsonify(payload)

    @app.post("/api/plugin/use")
    @app.post("/api/builder-core/meta/plugins/use")
    def meta_plugin_use():
        """Installed pack, no draft → New with that pack's Desc skeleton + pane."""
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from desktop.meta_store import data_dir, save_draft, unused_slug
        from plugin_catalog import (
            PluginError,
            catalog,
            installed_index,
            pack_document_code,
            pack_view_id,
            remember_plugin_draft,
            view_id_from_form,
        )

        body = request.get_json(silent=True) or {}
        ident = str(body.get("id") or "").strip()
        pack = next((row for row in catalog(include_pending=True, data_root=data_dir()) if row["id"] == ident), None)
        if not pack:
            return jsonify({"error": "unknown pack"}), 404
        if ident not in set(installed_index(data_dir())):
            return jsonify({"error": "install this plugin first"}), 400
        view = str(pack.get("view") or "") or pack_view_id(pack) or view_id_from_form(
            str(pack.get("form") or ""), str(pack.get("kindValue") or ident.replace("official-", ""))
        )
        from plugin_catalog import plugin_drafts, record_plugin_rebind

        old_bound = plugin_drafts(data_dir()).get(ident) or ""
        try:
            slug = unused_slug()
            code = pack_document_code(pack)
            save_draft(slug, code=code, current=True)
            remember_plugin_draft(data_dir(), ident, slug)
            if old_bound and old_bound != slug:
                record_plugin_rebind(data_dir(), ident, old_bound, slug)
            elif not old_bound:
                record_plugin_rebind(data_dir(), ident, "", slug)
        except (PluginError, MetaStoreError, InstantiationError, OSError, ValueError, TypeError) as exc:
            return jsonify({"error": str(exc)}), 400
        pane = view or "code"
        studio = "/studio/meta/" + slug + (("?pane=" + pane) if pane and pane != "code" else "")
        return jsonify(
            {
                "draft": slug,
                "draft_slug": slug,
                "from": old_bound,
                "pane": pane,
                "rebound": True,
                "slug": slug,
                "studio": studio,
                "to": slug,
            }
        )
    @app.get("/api/plugin/stamp-target")
    @app.get("/api/builder-core/meta/plugins/stamp-target")
    def meta_plugin_stamp_target():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from desktop.meta_store import data_dir
        from plugin_catalog import stamp_target

        name = str(request.args.get("name") or "").strip()
        ident, existing = stamp_target(name, data_root=data_dir())
        return jsonify({"id": ident, "overwrite": bool(existing), "replaced": bool(existing)})

    @app.get("/api/plugin/rebind-timeline")
    @app.get("/api/builder-core/meta/plugins/rebind-timeline")
    def meta_plugin_rebind_timeline():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from desktop.meta_store import data_dir
        from plugin_catalog import rebind_timeline

        return jsonify({"rows": rebind_timeline(data_dir())})

    @app.post("/api/plugin/disable")
    @app.post("/api/builder-core/meta/plugins/disable")
    def meta_plugin_disable():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import PluginError, uninstall_plugin

        from desktop.meta_store import data_dir

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(uninstall_plugin(data_dir(), str(body.get("id") or ""), delete=False))
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/plugin/timeline/restore")
    @app.post("/api/builder-core/meta/plugins/timeline/restore")
    def meta_plugin_timeline_restore():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import PluginError, restore_stamp_document

        from desktop.meta_store import data_dir

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                restore_stamp_document(
                    data_dir(),
                    slug=str(body.get("slug") or ""),
                    fingerprint=str(body.get("fingerprint") or ""),
                )
            )
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/plugin/remove")
    @app.post("/api/builder-core/meta/plugins/remove")
    def meta_plugin_remove():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import PluginError, plugin_drafts, uninstall_plugin

        from desktop.meta_store import data_dir, delete_draft

        body = request.get_json(silent=True) or {}
        ident = str(body.get("id") or "")
        delete_draft_flag = bool(body.get("delete_draft"))
        try:
            out = uninstall_plugin(data_dir(), ident, delete=True, delete_draft=delete_draft_flag)
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400
        if delete_draft_flag:
            slug = str(out.get("draft_slug") or plugin_drafts(data_dir()).get(ident) or "")
            if slug:
                try:
                    delete_draft(slug)
                    out["draft_deleted"] = True
                except (MetaStoreError, InstantiationError):
                    out["draft_deleted"] = False
        from desktop.meta_store import rebuild_search_index

        rebuild_search_index(base=data_dir())
        return jsonify(out)

    @app.post("/api/plugin/review")
    def meta_plugin_review():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import PluginError, review

        body = request.get_json(silent=True) or {}
        try:
            return jsonify(review(str(body.get("id") or ""), str(body.get("status") or "")))
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/plugin/store")
    def meta_plugin_store():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from plugin_catalog import hosted_catalog

        return jsonify(hosted_catalog())

    @app.post("/api/plugin/store")
    def meta_plugin_store_fetch():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from plugin_catalog import PluginError, fetch_store

        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"packs": fetch_store(str(body.get("url") or ""))})
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/plugin/store/mirror")
    def meta_plugin_store_mirror():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import mirror_catalog

        from desktop.meta_store import data_dir

        path = mirror_catalog(data_dir())
        return jsonify({"ok": True, "path": str(path)})

    @app.post("/api/plugin/store/install")
    def meta_plugin_store_install():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import record_install

        from desktop.meta_store import data_dir

        body = request.get_json(silent=True) or {}
        rows = record_install(data_dir(), str(body.get("id") or ""))
        return jsonify({"installed": rows})

    @app.post("/api/plugin/store/delta")
    def meta_plugin_store_delta():
        if not desktop_enabled():
            abort(404)
        context("builder.read")
        from plugin_catalog import catalog_delta, load_mirror

        from desktop.meta_store import data_dir

        return jsonify(catalog_delta(load_mirror(data_dir())))

    @app.post("/api/plugin/store/queue")
    def meta_plugin_store_queue():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import queue_pack, signed_index

        from desktop.meta_store import data_dir

        body = request.get_json(silent=True) or {}
        rows = queue_pack(data_dir(), str(body.get("id") or ""))
        return jsonify({"index": signed_index(data_dir()), "queue": rows})

    @app.post("/api/plugin/submit")
    @app.post("/api/builder-core/meta/plugins/submit")
    def meta_plugin_submit():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from plugin_catalog import PluginError, submit

        body = request.get_json(silent=True) or {}
        try:
            pack = submit(body.get("manifest") or body)
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(pack), 201

    @app.post("/api/plugin/project")
    @app.post("/api/builder-core/meta/plugins/project")
    def meta_plugin_project():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from desktop.meta_store import data_dir, save_artifact, save_draft
        from plugin_catalog import PluginError, catalog, installable, installed_index, plugin_drafts, plugin_key_slug, project_from_packs, remember_plugin_draft, view_id_from_form
        from meta.runtime.desktop_host import apply_desktop_host
        from meta.description import to_json

        body = request.get_json(silent=True) or {}
        wanted = body.get("ids") if isinstance(body.get("ids"), list) else installed_index(data_dir())
        wanted_ids = {str(item) for item in wanted}
        packs = [row for row in catalog(include_pending=True) if row["id"] in wanted_ids and installable(row)]
        try:
            desc = project_from_packs(packs, title=str(body.get("title") or (packs[0].get("name") if packs else "plugin-project")))
        except PluginError as exc:
            return jsonify({"error": str(exc)}), 400
        mapped = plugin_drafts(data_dir()).get(str((packs[0] or {}).get("id") or "")) if packs else ""
        slug = str(body.get("slug") or mapped or (plugin_key_slug(packs[0]) if packs else "plugin-project"))
        artifact = instantiate(desc, target=TARGET_DESKTOP_HOST, slug=slug)
        save_artifact(artifact)
        save_draft(artifact.slug or slug, code=to_json(desc, indent=2), current=True)
        for pack in packs:
            remember_plugin_draft(data_dir(), str(pack.get("id") or ""), artifact.slug or slug)
        stored = apply_desktop_host(
            desc,
            slug=artifact.slug or slug,
            data_root=data_dir(),
            parts=artifact.payload_object().get("parts") if artifact.payload_object() else None,
        )
        pane = ""
        if packs:
            pane = str(packs[0].get("view") or "") or view_id_from_form(str(packs[0].get("form") or ""), str(packs[0].get("kindValue") or ""))
        studio = f"/studio/meta/{artifact.slug or slug}" + (f"?pane={pane}" if pane else "")
        return jsonify(
            {
                "cdn": False,
                "loop": "plugin-project-plugin",
                "pane": pane or "code",
                "public_url": artifact.public_url,
                "slug": artifact.slug,
                "studio": studio,
                "unity": False,
                "wan": False,
                "host": stored.get("host"),
            }
        ), 201

    @app.post("/api/ai")
    @app.post("/api/ai/chat")
    @app.post("/api/builder-core/meta/ai")
    @app.post("/api/builder-core/meta/ai/chat")
    def meta_ai():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from pathlib import Path

        from meta.runtime.kernels import WeightsError, complete_session, complete_session_stream
        from meta.runtime.local_infer import DEFAULT_MODEL, resolve_model_path

        body = request.get_json(silent=True) or {}
        try:
            from desktop.meta_store import data_dir

            root = Path(data_dir())
            model = str(body.get("model") or DEFAULT_MODEL)
            resolve_model_path(root, model)
            kwargs = {
                "prompt": str(body.get("prompt") or ""),
                "messages": body.get("messages") if isinstance(body.get("messages"), list) else None,
                "data_root": root,
                "name": model,
                "temperature": float(body.get("temperature") or 0.7),
                "max_tokens": int(body.get("max_tokens") or 256),
                "system": str(body.get("system") or ""),
                "context": int(body.get("context") or 2048),
            }
            if body.get("stream"):
                def generate():
                    try:
                        for chunk in complete_session_stream(**kwargs):
                            yield json.dumps(chunk) + "\n"
                    except WeightsError as exc:
                        yield json.dumps({"error": str(exc), "hosted": False, "local": True}) + "\n"

                return Response(stream_with_context(generate()), mimetype="application/x-ndjson")
            session = complete_session(**kwargs)
        except WeightsError as exc:
            return jsonify({"error": str(exc), "hosted": False, "local": True}), 404
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(session)

    @app.post("/api/ai/embed")
    @app.post("/api/builder-core/meta/ai/embed")
    def meta_ai_embed():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from pathlib import Path

        from meta.runtime.kernels import WeightsError
        from meta.runtime.local_infer import DEFAULT_MODEL, embed_local

        body = request.get_json(silent=True) or {}
        try:
            from desktop.meta_store import data_dir

            session = embed_local(
                str(body.get("text") or body.get("prompt") or ""),
                data_root=Path(data_dir()),
                name=str(body.get("model") or DEFAULT_MODEL),
                dim=int(body.get("dim") or 8),
            )
        except WeightsError as exc:
            return jsonify({"error": str(exc), "hosted": False, "local": True}), 404
        except MetaStoreError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(session)

    @app.post("/api/ai/tools")
    @app.post("/api/builder-core/meta/ai/tools")
    def meta_ai_tools():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from pathlib import Path

        from meta.runtime.ai_tools import run_tool
        from meta.runtime.kernels import WeightsError
        from meta.runtime.local_infer import DEFAULT_MODEL

        body = request.get_json(silent=True) or {}
        try:
            from desktop.meta_store import data_dir

            result = run_tool(
                str(body.get("tool") or body.get("name") or ""),
                body.get("args") if isinstance(body.get("args"), dict) else body,
                code=str(body.get("code") or ""),
                data_root=Path(data_dir()),
                model=str(body.get("model") or DEFAULT_MODEL),
            )
        except WeightsError as exc:
            return jsonify({"error": str(exc), "hosted": False, "local": True, "ok": False}), 404
        except MetaStoreError as exc:
            return jsonify({"error": str(exc), "ok": False}), 400
        status = 200 if result.get("ok") else 400
        if result.get("error") and "weights" in str(result.get("error")).lower():
            status = 404
        return jsonify(result), status

    @app.post("/api/builder-core/meta/engine/play")
    def meta_engine_play():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from meta.runtime.engine import play_from_system, stop_session

        body = request.get_json(silent=True) or {}
        try:
            desc = _desc_from_body(body)
            if body.get("stop"):
                return jsonify(stop_session({"t": float(body.get("t") or 0)}))
            session = play_from_system(desc, frames=int(body.get("frames") or 2), dt=float(body.get("dt") or (1.0 / 60.0)))
        except (DescriptionError, InstantiationError, ValueError) as exc:
            return jsonify({"error": str(exc), "unity": False}), 400
        return jsonify(session)

    @app.post("/api/builder-core/meta/world/place")
    def meta_world_place():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from pathlib import Path

        from meta.collab.loopback import replicate_place
        from meta.runtime.world import copy_object, place_spec, replicate_objects

        body = request.get_json(silent=True) or {}
        try:
            desc = _desc_from_body(body)
            spec = place_spec(desc)
            if body.get("copy"):
                spec["objects"] = [copy_object(row) for row in spec.get("objects") or []]
            remote = body.get("remote") if isinstance(body.get("remote"), list) else []
            spec["objects"] = replicate_objects(spec.get("objects"), remote)
            from desktop.meta_store import data_dir

            status = replicate_place(Path(data_dir()), spec)
            spec["replica"] = status
        except (DescriptionError, InstantiationError, ValueError) as exc:
            return jsonify({"error": str(exc), "roblox": False, "wan": False}), 400
        return jsonify(spec)

    @app.post("/api/deploy")
    def meta_deploy():
        if not desktop_enabled():
            abort(404)
        return jsonify({"error": "use /api/builder-core/meta/instantiate"}), 400

    @app.get("/api/hardware")
    def meta_hardware_alias():
        if not desktop_enabled():
            abort(404)
        return redirect("/api/builder-core/meta/hardware")

    @app.post("/api/builder-core/meta/collab/loopback")
    def meta_collab_loopback():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        from meta.collab.loopback import LoopbackError, exchange_peers, register_peer

        from desktop.meta_store import data_dir

        body = request.get_json(silent=True) or {}
        try:
            if body.get("peer"):
                register_peer(data_dir(), str(body.get("peer") or ""))
            return jsonify(exchange_peers(data_dir()))
        except LoopbackError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/meta/collab/record")
    def meta_collab_record():
        if not desktop_enabled():
            abort(404)
        context("builder.update")
        body = request.get_json(silent=True) or {}
        slug = str(body.get("slug") or "")
        from desktop.meta_store import data_dir

        folder = data_dir() / "collab-record"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{slug or 'session'}.jsonl"
        line = json.dumps({"at": body.get("at"), "op": body.get("op")}, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return jsonify({"ok": True})

