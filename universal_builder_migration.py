"""Central route ownership and strangler-runtime resolution for Phase 3."""

from __future__ import annotations

import json
import logging


_log = logging.getLogger("app.universal_builder")

RENDERER_TYPES = {"native_document", "legacy_adapter", "hybrid_document", "capability_module"}
MIGRATION_STATES = {"legacy", "adapted", "hybrid", "native"}


def _json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        _log.debug("builder_migration_json_parse_failed", exc_info=True, extra={"op": "json"})
        return fallback


def validate_route_ownership(conn, project_id: int) -> list[dict]:
    from universal_component_registry import COMPONENT_REGISTRY
    from universal_builder_modules import APP_MODULE_REGISTRY, DATA_SOURCE_REGISTRY

    issues: list[dict] = []
    rows = conn.execute("SELECT * FROM builder_route_ownership WHERE project_id=?", (project_id,)).fetchall()
    seen = set()
    for row in rows:
        if row["route"] in seen:
            issues.append({"level": "error", "code": "duplicate_route", "message": f"Duplicate route {row['route']}"})
        seen.add(row["route"])
        if row["renderer_type"] not in RENDERER_TYPES:
            issues.append({"level": "error", "code": "renderer", "message": f"Unknown renderer {row['renderer_type']}"})
        if row["migration_status"] not in MIGRATION_STATES:
            issues.append({"level": "error", "code": "migration_status", "message": f"Unknown migration status {row['migration_status']}"})
        document = conn.execute("SELECT * FROM builder_documents WHERE id=? AND project_id=?", (row["document_id"], project_id)).fetchone()
        if not document:
            issues.append({"level": "error", "code": "missing_document", "message": f"{row['route']} has no Document"})
            continue
        nodes = conn.execute("SELECT * FROM builder_nodes WHERE document_id=?", (document["id"],)).fetchall()
        for node in nodes:
            if node["component_type"] not in COMPONENT_REGISTRY:
                issues.append({"level": "error", "code": "component", "message": f"Unknown component {node['component_type']}"})
            props = _json(node["props"], {})
            if node["component_type"] == "app_module" and props.get("module_id") not in APP_MODULE_REGISTRY:
                issues.append({"level": "error", "code": "module", "message": f"Unknown App Module {props.get('module_id')}"})
        bindings = conn.execute("SELECT * FROM builder_bindings WHERE project_id=? AND document_id=?", (project_id, document["id"])).fetchall()
        for binding in bindings:
            config = _json(binding["source_config"], {})
            if binding["source_type"] == "domain" and config.get("source_id") not in DATA_SOURCE_REGISTRY:
                issues.append({"level": "error", "code": "data_source", "message": f"Unknown Data Source {config.get('source_id')}"})
    return issues


def resolve_route(conn, route: str, *, workspace_id: int | None = None):
    params: list = [route]
    workspace_clause = ""
    if workspace_id is not None:
        workspace_clause = " AND p.workspace_id=?"
        params.append(workspace_id)
    return conn.execute(
        f"""SELECT o.*,p.workspace_id,p.slug AS project_slug,p.settings AS project_settings,
                   d.document_key,d.schema AS document_schema,dep.revision_id,dep.adapter AS deployment_adapter,
                   r.snapshot
            FROM builder_route_ownership o
            JOIN builder_projects p ON p.id=o.project_id
            JOIN builder_documents d ON d.id=o.document_id
            JOIN builder_deployments dep ON dep.project_id=p.id AND dep.environment='production'
              AND dep.channel='web' AND dep.status='active' AND dep.revision_id IS NOT NULL
            JOIN builder_project_revisions r ON r.id=dep.revision_id
            WHERE o.route=? AND o.status='active'{workspace_clause}
            ORDER BY o.priority DESC,o.updated_at DESC,o.id DESC LIMIT 1""",
        params,
    ).fetchone()


def render_owned_route(conn, route: str, *, workspace_id: int | None = None, locale: str = "en", csrf: str = "",
                       public: bool = False, notice: str = ""):
    """Return a rendered Flask Response, or None so the caller uses legacy fallback."""
    from flask import Response, current_app
    from universal_builder_modules import collect_snapshot_domain_sources, load_domain_data
    from universal_builder_runtime import render_document

    ownership = resolve_route(conn, route, workspace_id=workspace_id)
    if not ownership:
        return None
    try:
        snapshot = _json(ownership["snapshot"], {})
        if not any((item.get("key") or item.get("document_key")) == ownership["document_key"] for item in snapshot.get("documents") or []):
            raise ValueError("Published revision does not contain the owned Document")
        domain_data = {}
        for source_id, query in collect_snapshot_domain_sources(snapshot).items():
            domain_data[source_id] = load_domain_data(
                conn, source_id, workspace_id=int(ownership["workspace_id"]), query=query, public=public,
            )
        output = render_document(
            snapshot, ownership["document_key"], csrf=csrf, locale=locale,
            domain_data=domain_data, route_path=route, notice=notice,
        )
        if output is None:
            raise ValueError("Runtime could not render the owned Document")
        conn.execute(
            """INSERT INTO builder_runtime_events(project_id,document_id,event_type,route,source,metadata)
               VALUES (?,?,'view',?,'hybrid',?)""",
            (ownership["project_id"], ownership["document_id"], route,
             json.dumps({"renderer": ownership["renderer_type"], "migration_status": ownership["migration_status"]})),
        )
        response = Response(output, mimetype="text/html")
        response.headers["X-Universal-Builder-Renderer"] = ownership["renderer_type"]
        response.headers["X-Universal-Builder-Migration"] = ownership["migration_status"]
        return response
    except Exception as error:
        current_app.logger.error("Universal Builder route fallback for %s: %s", route, error)
        return None
