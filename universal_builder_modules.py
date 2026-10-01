"""Controlled App Module and domain Data Source contracts for Phase 3.

These registries expose mature systems to the Builder without copying their
storage or granting access merely because a Node references them.
"""

from __future__ import annotations

from copy import deepcopy


APP_MODULE_REGISTRY: dict[str, dict] = {
    "commerce.store_manager": {
        "id": "commerce.store_manager",
        "namespace": "commerce",
        "name": "Store Manager",
        "version": 1,
        "kind": "app_module",
        "required_capabilities": ["commerce", "auth"],
        "permission": "catalog.read",
        "supported_surfaces": ["business"],
        "configuration_schema": {
            "type": "object",
            "properties": {
                "default_tab": {"type": "string", "enum": ["stores", "experiences", "responses"]},
                "show_header": {"type": "boolean"},
            },
        },
        "editor_render_mode": "controlled_frame",
        "runtime_render_mode": "controlled_frame",
        "runtime_adapter": "bos.store",
        "legacy_adapter": "bos.store_module",
        "manager_url": "/app/store?legacy=1",
        "events": ["store.created", "store.updated", "qr.published"],
        "actions": ["open_manager"],
        "data_dependencies": ["commerce.stores"],
        "security_class": "workspace_module",
        "migration_metadata": {"status": "adapted", "fallback": "/app/store"},
    },
    "booking.manager": {
        "id": "booking.manager", "namespace": "booking", "name": "Booking Manager", "version": 1,
        "kind": "app_module", "required_capabilities": ["booking", "auth"],
        "permission": "booking.read", "supported_surfaces": ["business"],
        "configuration_schema": {"type": "object", "properties": {}},
        "editor_render_mode": "open_manager", "runtime_render_mode": "open_manager",
        "runtime_adapter": "booking_platform", "legacy_adapter": "booking_platform",
        "manager_url": "/app/booking", "events": ["booking.created", "booking.updated"],
        "actions": ["open_manager"], "data_dependencies": ["booking.records"],
        "security_class": "workspace_module", "migration_metadata": {"status": "adapted"},
    },
    "analytics.dashboard": {
        "id": "analytics.dashboard", "namespace": "analytics", "name": "Analytics Dashboard", "version": 1,
        "kind": "app_module", "required_capabilities": ["analytics", "auth"],
        "permission": "analytics.read", "supported_surfaces": ["business"],
        "configuration_schema": {"type": "object", "properties": {"period": {"type": "string"}}},
        "editor_render_mode": "open_manager", "runtime_render_mode": "open_manager",
        "runtime_adapter": "qr_experience_analytics", "legacy_adapter": "qr_experience_analytics",
        "manager_url": "/app/store#experiences", "events": [], "actions": ["open_manager"],
        "data_dependencies": ["qr.analytics"], "security_class": "workspace_module",
        "migration_metadata": {"status": "adapted"},
    },
}


DATA_SOURCE_REGISTRY: dict[str, dict] = {
    "commerce.stores": {
        "id": "commerce.stores", "namespace": "Commerce", "name": "Stores",
        "kind": "collection", "permission": None, "public": True, "read_only": True,
        "fields": {
            "id": "number", "slug": "string", "name": "string", "description": "string",
            "logo_url": "url", "background_image": "url", "address": "string", "status": "string",
        },
        "query": {"filters": ["status", "discoverable"], "sort": ["name", "created_at"], "max_limit": 24},
        "runtime_adapter": "stores", "canonical_table": "stores",
    },
    "commerce.products": {
        "id": "commerce.products", "namespace": "Commerce", "name": "Products",
        "kind": "collection", "permission": None, "public": True, "read_only": True,
        "fields": {
            "id": "number", "store_id": "number", "name": "string", "description": "string",
            "price": "number", "image_url": "url", "status": "string", "allow_cart": "boolean",
        },
        "query": {"filters": ["store_id", "status"], "sort": ["display_order", "name", "price"], "max_limit": 48},
        "runtime_adapter": "items", "canonical_table": "items",
    },
    "workspace.current": {
        "id": "workspace.current", "namespace": "Workspace", "name": "Current workspace",
        "kind": "resource", "permission": "workspace.read", "public": False, "read_only": True,
        "fields": {"id": "number", "name": "string", "slug": "string"},
        "query": {"filters": [], "sort": [], "max_limit": 1},
        "runtime_adapter": "workspaces", "canonical_table": "workspaces",
    },
}


def app_module_payload(identifier: str | None = None):
    if identifier:
        value = APP_MODULE_REGISTRY.get(identifier)
        return deepcopy(value) if value else None
    return deepcopy(APP_MODULE_REGISTRY)


def data_source_payload(identifier: str | None = None):
    if identifier:
        value = DATA_SOURCE_REGISTRY.get(identifier)
        return deepcopy(value) if value else None
    return deepcopy(DATA_SOURCE_REGISTRY)


def _safe_limit(spec: dict, query: dict) -> int:
    maximum = int(spec.get("query", {}).get("max_limit", 24))
    return max(1, min(int(query.get("limit") or maximum), maximum))


def load_domain_data(conn, source_id: str, *, workspace_id: int, query: dict | None = None, public: bool = False):
    """Load an allow-listed projection from canonical domain storage."""
    spec = DATA_SOURCE_REGISTRY.get(source_id)
    if not spec:
        raise ValueError("Unknown data source")
    if public and not spec.get("public"):
        raise PermissionError("This data source is not public")
    query = query or {}
    limit = _safe_limit(spec, query)
    if source_id == "commerce.stores":
        where, values = ["workspace_id=?"], [workspace_id]
        status = str(query.get("status") or "active")
        if status: where.append("status=?"); values.append(status)
        if query.get("discoverable") is not None:
            where.append("discoverable=?"); values.append(1 if query.get("discoverable") else 0)
        rows = conn.execute(
            f"""SELECT id,slug,name,COALESCE(description,'') AS description,COALESCE(logo_url,'') AS logo_url,
                       COALESCE(background_image,'') AS background_image,COALESCE(address,'') AS address,status
                FROM stores WHERE {' AND '.join(where)} ORDER BY name COLLATE NOCASE LIMIT ?""",
            [*values, limit],
        ).fetchall()
        return [dict(row) for row in rows]
    if source_id == "commerce.products":
        where, values = ["s.workspace_id=?"], [workspace_id]
        if query.get("store_id"):
            where.append("i.store_id=?"); values.append(int(query["store_id"]))
        status = str(query.get("status") or "published")
        if status: where.append("i.status=?"); values.append(status)
        rows = conn.execute(
            f"""SELECT i.id,i.store_id,i.name,COALESCE(i.description,'') AS description,i.price,
                       COALESCE(i.image_url,'') AS image_url,i.status,i.allow_cart
                FROM items i JOIN stores s ON s.id=i.store_id WHERE {' AND '.join(where)}
                ORDER BY i.display_order,i.name COLLATE NOCASE LIMIT ?""",
            [*values, limit],
        ).fetchall()
        return [dict(row) for row in rows]
    if source_id == "workspace.current":
        row = conn.execute("SELECT id,name,slug FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        return dict(row) if row else None
    raise ValueError("Data source adapter is not implemented")


def collect_snapshot_domain_sources(snapshot: dict) -> dict[str, dict]:
    """Return source/query pairs referenced by a snapshot without executing them."""
    result: dict[str, dict] = {}
    for binding in snapshot.get("bindings") or []:
        if binding.get("source_type") != "domain":
            continue
        config = binding.get("source_config")
        if isinstance(config, str):
            import json
            try: config = json.loads(config)
            except (TypeError, json.JSONDecodeError): config = {}
        source_id = (config or {}).get("source_id")
        if source_id in DATA_SOURCE_REGISTRY:
            result[source_id] = (config or {}).get("query") or {}
    for node in snapshot.get("nodes") or []:
        if node.get("component_type") == "store_grid":
            result.setdefault("commerce.stores", {})
    return result
