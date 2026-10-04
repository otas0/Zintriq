"""Universal Builder Core.

The core is additive: existing Zintriq platforms remain the runtime while a
generic project/document/node model is introduced around them.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_log = logging.getLogger("app.universal_builder")


ROOT = Path(__file__).resolve().parent
OFFICIAL_TEMPLATE_PATH = ROOT / "builder_templates" / "zintriq-system" / "manifest.json"

CORE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS builder_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    publisher TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    schema_version INTEGER NOT NULL DEFAULT 1,
    template_kind TEXT NOT NULL DEFAULT 'application',
    source TEXT NOT NULL DEFAULT 'community',
    visibility TEXT NOT NULL DEFAULT 'community',
    status TEXT NOT NULL DEFAULT 'active',
    marketplace_ready INTEGER NOT NULL DEFAULT 0,
    package_path TEXT DEFAULT '',
    manifest TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS builder_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    template_id TEXT,
    template_version INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'application',
    status TEXT NOT NULL DEFAULT 'draft',
    settings TEXT NOT NULL DEFAULT '{}',
    created_by INTEGER,
    legacy_source_type TEXT,
    legacy_source_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(workspace_id, slug),
    UNIQUE(workspace_id, legacy_source_type, legacy_source_id),
    FOREIGN KEY(template_id) REFERENCES builder_templates(id)
);
CREATE INDEX IF NOT EXISTS idx_builder_projects_workspace ON builder_projects(workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS builder_surfaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    surface_key TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'public_web',
    audience TEXT NOT NULL DEFAULT 'public',
    base_path TEXT DEFAULT '',
    settings TEXT NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id, surface_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    document_key TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'page',
    route TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    schema TEXT NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    legacy_source_type TEXT,
    legacy_source_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id, document_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    node_key TEXT NOT NULL,
    parent_key TEXT,
    component_type TEXT NOT NULL,
    props TEXT NOT NULL DEFAULT '{}',
    styles TEXT NOT NULL DEFAULT '{}',
    responsive TEXT NOT NULL DEFAULT '{}',
    translations TEXT NOT NULL DEFAULT '{}',
    position TEXT NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(document_id, node_key),
    FOREIGN KEY(document_id) REFERENCES builder_documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    document_id INTEGER,
    node_key TEXT,
    binding_key TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_config TEXT NOT NULL DEFAULT '{}',
    transform TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id, document_id, node_key, binding_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    document_id INTEGER,
    node_key TEXT,
    action_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    action_type TEXT NOT NULL,
    configuration TEXT NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id, action_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    environment TEXT NOT NULL DEFAULT 'production',
    channel TEXT NOT NULL DEFAULT 'web',
    status TEXT NOT NULL DEFAULT 'draft',
    adapter TEXT NOT NULL DEFAULT 'native',
    public_url TEXT DEFAULT '',
    revision_id INTEGER,
    configuration TEXT NOT NULL DEFAULT '{}',
    deployed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id, environment, channel),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_project_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    revision_number INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'draft',
    snapshot TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, revision_number),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_data_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    model_key TEXT NOT NULL,
    name TEXT NOT NULL,
    schema TEXT NOT NULL DEFAULT '{}',
    adapter TEXT NOT NULL DEFAULT 'native',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id, model_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_data_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    model_key TEXT NOT NULL,
    record_key TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    surface TEXT NOT NULL DEFAULT 'preview',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id, model_key, record_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_state_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    state_key TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'project',
    initial_value TEXT NOT NULL DEFAULT 'null',
    value_schema TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, state_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    condition_key TEXT NOT NULL,
    name TEXT NOT NULL,
    expression TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, condition_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_entry_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    surface_id INTEGER,
    document_id INTEGER,
    entry_type TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    configuration TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(entry_type, entry_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_packages (
    id TEXT PRIMARY KEY,
    package_type TEXT NOT NULL,
    publisher TEXT NOT NULL,
    version INTEGER NOT NULL,
    manifest TEXT NOT NULL,
    trust_level TEXT NOT NULL DEFAULT 'community',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS builder_package_installations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    package_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    granted_permissions TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    installed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, package_id),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(package_id) REFERENCES builder_packages(id)
);

CREATE TABLE IF NOT EXISTS builder_route_ownership (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    surface_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    route TEXT NOT NULL,
    renderer_type TEXT NOT NULL DEFAULT 'legacy_adapter',
    migration_status TEXT NOT NULL DEFAULT 'legacy',
    legacy_fallback TEXT DEFAULT '',
    configuration TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id, route),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(surface_id) REFERENCES builder_surfaces(id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES builder_documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_builder_route_resolution ON builder_route_ownership(route,status,priority DESC);

CREATE TABLE IF NOT EXISTS builder_runtime_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    document_id INTEGER,
    event_type TEXT NOT NULL,
    route TEXT DEFAULT '',
    source TEXT NOT NULL DEFAULT 'native',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_builder_runtime_events_project ON builder_runtime_events(project_id,created_at DESC);

CREATE TABLE IF NOT EXISTS builder_kernel_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    action_id TEXT NOT NULL DEFAULT '',
    node_key TEXT DEFAULT '',
    action_key TEXT DEFAULT '',
    record_key TEXT DEFAULT '',
    status TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_builder_kernel_events_project ON builder_kernel_events(project_id, id DESC);

CREATE TABLE IF NOT EXISTS builder_component_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    component_key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    root_structure TEXT NOT NULL DEFAULT '[]',
    property_schema TEXT NOT NULL DEFAULT '{}',
    slots TEXT NOT NULL DEFAULT '{}',
    variants TEXT NOT NULL DEFAULT '{}',
    default_variant TEXT NOT NULL DEFAULT 'default',
    data_inputs TEXT NOT NULL DEFAULT '{}',
    events TEXT NOT NULL DEFAULT '[]',
    token_dependencies TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id,component_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_component_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    node_key TEXT NOT NULL,
    component_definition_id INTEGER NOT NULL,
    variant TEXT NOT NULL DEFAULT 'default',
    overrides TEXT NOT NULL DEFAULT '{}',
    slot_content TEXT NOT NULL DEFAULT '{}',
    bindings TEXT NOT NULL DEFAULT '{}',
    responsive TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id,document_id,node_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES builder_documents(id) ON DELETE CASCADE,
    FOREIGN KEY(component_definition_id) REFERENCES builder_component_definitions(id)
);

CREATE TABLE IF NOT EXISTS builder_design_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    token_key TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    group_name TEXT DEFAULT '',
    values_json TEXT NOT NULL DEFAULT '{}',
    description TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id,token_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_project_variables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    variable_key TEXT NOT NULL,
    name TEXT NOT NULL,
    value_json TEXT NOT NULL DEFAULT 'null',
    value_type TEXT NOT NULL DEFAULT 'string',
    group_name TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id,variable_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS builder_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    document_id INTEGER,
    node_key TEXT,
    interaction_key TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    interaction_type TEXT NOT NULL,
    configuration TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(project_id,interaction_key),
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        _log.debug("builder_core_json_parse_failed", exc_info=True, extra={"op": "json"})
        return fallback


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "project").lower()).strip("-")
    return slug or "project"


_ROUTE_PATTERN = re.compile(r"^/[A-Za-z0-9_\-./:{}*]*$")


def _normalize_route(value: str) -> str:
    """Collapse the many textual forms of a route into one canonical representation.

    `/about`, `about`, `/about/` and `//about` all normalize to `/about`; the root stays `/`.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    while "//" in raw:
        raw = raw.replace("//", "/")
    if len(raw) > 1:
        raw = raw.rstrip("/") or "/"
    return raw


def _validate_document_route(conn, project_id: int, raw_route, exclude_document_id=None, allow_empty: bool = False, surface_id=None):
    """Return (route, None) when valid, or (None, (error_payload, status)) when not.

    Uniqueness is enforced across the live (status='active') pages of the same surface, so exactly
    one page per site owns `/`. Validation runs server-side; the browser is never the only boundary.
    """
    route = _normalize_route(raw_route)
    if not route:
        if allow_empty:
            return "", None
        return None, ({"error": "Route cannot be empty. Use / for the home page or a path like /about."}, 400)
    if not _ROUTE_PATTERN.match(route):
        return None, ({"error": "This route has invalid characters. Use letters, numbers, and - _ / : . only."}, 400)
    existing = conn.execute(
        "SELECT id, name FROM builder_documents WHERE project_id=? AND route=? AND status='active' AND surface_id IS ? AND (? IS NULL OR id != ?)",
        (project_id, route, surface_id, exclude_document_id, exclude_document_id),
    ).fetchone()
    if existing:
        return None, ({"error": f"This route is already used by another page ({existing['name']})."}, 409)
    return route, None


def _unique_document_route(conn, project_id: int, base_route: str, surface_id=None) -> str:
    normalized = _normalize_route(base_route) or "/page"
    route = normalized
    suffix = 2
    while conn.execute("SELECT 1 FROM builder_documents WHERE project_id=? AND route=? AND status='active' AND surface_id IS ?", (project_id, route, surface_id)).fetchone():
        route = f"{normalized}-{suffix}"
        suffix += 1
    return route


def official_system_manifest() -> dict:
    return json.loads(OFFICIAL_TEMPLATE_PATH.read_text(encoding="utf-8"))


def validate_template_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []
    for key in ("id", "name", "publisher", "version", "schema_version", "template_kind", "documents"):
        if manifest.get(key) in (None, "", []):
            errors.append(f"Missing {key}")
    if not isinstance(manifest.get("documents"), list):
        errors.append("documents must be a list")
    else:
        keys = [item.get("key") for item in manifest["documents"] if isinstance(item, dict)]
        if len(keys) != len(set(keys)):
            errors.append("document keys must be unique")
    return errors


def seed_official_system_template(conn) -> None:
    from universal_builder_packages import validate_package_manifest

    manifest = official_system_manifest()
    errors = validate_template_manifest(manifest)
    errors.extend(validate_package_manifest(manifest))
    if errors:
        raise ValueError(f"Invalid official Builder template: {', '.join(errors)}")
    conn.execute(
        """INSERT INTO builder_templates
           (id, name, description, publisher, version, schema_version, template_kind,
            source, visibility, status, marketplace_ready, package_path, manifest, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name, description=excluded.description, publisher=excluded.publisher,
             version=excluded.version, schema_version=excluded.schema_version,
             template_kind=excluded.template_kind, source=excluded.source,
             visibility=excluded.visibility, marketplace_ready=excluded.marketplace_ready,
             package_path=excluded.package_path, manifest=excluded.manifest,
             status='active', updated_at=excluded.updated_at""",
        (
            manifest["id"], manifest["name"], manifest.get("description", ""),
            manifest["publisher"], manifest["version"], manifest["schema_version"],
            manifest["template_kind"], manifest["source"], manifest["visibility"],
            int(bool(manifest.get("marketplace_ready"))),
            str(OFFICIAL_TEMPLATE_PATH.parent.relative_to(ROOT)),
            json.dumps(manifest), _now(),
        ),
    )
    conn.execute(
        """INSERT INTO builder_packages
           (id, package_type, publisher, version, manifest, trust_level, status, updated_at)
           VALUES (?, ?, ?, ?, ?, 'official', 'active', ?)
           ON CONFLICT(id) DO UPDATE SET package_type=excluded.package_type,
             publisher=excluded.publisher, version=excluded.version, manifest=excluded.manifest,
             trust_level='official', status='active', updated_at=excluded.updated_at""",
        (manifest["id"], manifest["package_type"], manifest["publisher"], manifest["version"], json.dumps(manifest), _now()),
    )


def init_universal_builder_tables(conn) -> None:
    conn.executescript(CORE_SCHEMA_SQL)
    from builder_kernel.events import migrate_kernel_events
    from builder_kernel.records import migrate_record_surface

    migrate_kernel_events(conn)
    migrate_record_surface(conn)
    migrations = {
        "builder_projects": {
            "description": "TEXT DEFAULT ''", "schema_version": "INTEGER NOT NULL DEFAULT 1",
            "default_surface_id": "INTEGER", "enabled_capabilities": "TEXT NOT NULL DEFAULT '[]'",
            "theme_reference": "TEXT DEFAULT ''",
        },
        "builder_documents": {"surface_id": "INTEGER", "schema_version": "INTEGER NOT NULL DEFAULT 1"},
        "builder_nodes": {
            "component_reference": "TEXT DEFAULT ''", "slot": "TEXT DEFAULT 'default'",
            "visibility": "TEXT NOT NULL DEFAULT 'visible'", "condition_id": "INTEGER",
            "permissions": "TEXT NOT NULL DEFAULT '[]'", "metadata": "TEXT NOT NULL DEFAULT '{}'",
            "schema_version": "INTEGER NOT NULL DEFAULT 2",
            "position": "TEXT NOT NULL DEFAULT '{}'",
        },
    }
    for table, columns in migrations.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    seed_official_system_template(conn)
    from universal_builder_marketplace import init_marketplace_tables
    init_marketplace_tables(conn)


def template_to_api(row, *, include_manifest: bool = True) -> dict:
    result = {
        "id": row["id"], "name": row["name"], "description": row["description"] or "",
        "publisher": row["publisher"], "version": row["version"],
        "schema_version": row["schema_version"], "template_kind": row["template_kind"],
        "source": row["source"], "visibility": row["visibility"], "status": row["status"],
        "is_official": row["visibility"] == "official", "marketplace_ready": bool(row["marketplace_ready"]),
        "package_path": row["package_path"] or "", "created_at": row["created_at"], "updated_at": row["updated_at"],
    }
    if include_manifest:
        result["manifest"] = _json(row["manifest"], {})
    return result


def get_template(conn, template_id: str):
    return conn.execute("SELECT * FROM builder_templates WHERE id=? AND status='active'", (template_id,)).fetchone()


def _workspace(conn, workspace_id: int):
    return conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()


def _insert_official_node(conn, document_id: int, key: str, component_type: str, *, parent_key=None,
                          slot="default", props=None, styles=None, responsive=None, translations=None,
                          order=0, metadata=None) -> None:
    from universal_component_registry import COMPONENT_REGISTRY

    spec = COMPONENT_REGISTRY[component_type]
    values = dict(spec.get("defaults") or {}); values.update(props or {})
    conn.execute(
        """INSERT OR IGNORE INTO builder_nodes
           (document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,responsive,
            translations,position,sort_order,visibility,permissions,metadata,schema_version,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'visible',?,?,2,?)""",
        (document_id, key, parent_key, component_type, spec["id"], slot, json.dumps(values), json.dumps(styles or {}),
         json.dumps(responsive or {}), json.dumps(translations or {}), json.dumps({}), order, json.dumps(spec.get("permissions") or []),
         json.dumps(metadata or {}), _now()),
    )


def _official_home_translations() -> dict:
    return {
        "zh-Hans": {"title": "发现身边的商店与体验", "body": "浏览商店、服务与活动，一切尽在一处。"},
        "zh-CN": {"title": "发现身边的商店与体验", "body": "浏览商店、服务与活动，一切尽在一处。"},
        "zh-Hant": {"title": "探索身邊的商店與體驗", "body": "瀏覽商店、服務與活動，一切盡在一處。"},
        "ja": {"title": "近くのお店と体験を見つけよう", "body": "お店、サービス、イベントをひとつの場所で探せます。"},
        "ms": {"title": "Temui kedai dan pengalaman berdekatan", "body": "Terokai kedai, perkhidmatan dan acara di satu tempat."},
        "id": {"title": "Temukan toko dan pengalaman di sekitar", "body": "Jelajahi toko, layanan, dan acara dalam satu tempat."},
        "ko": {"title": "주변 매장과 새로운 경험을 만나보세요", "body": "매장, 서비스와 이벤트를 한곳에서 둘러보세요."},
        "th": {"title": "ค้นพบร้านค้าและประสบการณ์ใกล้คุณ", "body": "สำรวจร้านค้า บริการ และกิจกรรมได้ในที่เดียว"},
        "vi": {"title": "Khám phá cửa hàng và trải nghiệm gần bạn", "body": "Tìm cửa hàng, dịch vụ và sự kiện ở cùng một nơi."},
        "fil": {"title": "Tuklasin ang mga tindahan at karanasan sa paligid", "body": "Hanapin ang mga tindahan, serbisyo, at event sa iisang lugar."},
        "es": {"title": "Descubre tiendas y experiencias cercanas", "body": "Explora tiendas, servicios y eventos en un solo lugar."},
        "pt-BR": {"title": "Descubra lojas e experiências perto de você", "body": "Explore lojas, serviços e eventos em um só lugar."},
        "fr": {"title": "Découvrez les boutiques et expériences autour de vous", "body": "Explorez boutiques, services et événements au même endroit."},
        "de": {"title": "Entdecke Geschäfte und Erlebnisse in deiner Nähe", "body": "Finde Geschäfte, Services und Events an einem Ort."},
        "ar": {"title": "اكتشف المتاجر والتجارب القريبة منك", "body": "استكشف المتاجر والخدمات والفعاليات في مكان واحد."},
        "sv": {"title": "Upptäck butiker och upplevelser nära dig", "body": "Utforska butiker, tjänster och evenemang på ett ställe."},
    }


def ensure_official_native_documents(conn, project_id: int, surface_ids: dict[str, int]) -> None:
    """Seed the first strangler slices once; subsequent edits remain user-owned."""
    customer = conn.execute(
        "SELECT * FROM builder_documents WHERE project_id=? AND document_key='customer-site'", (project_id,)
    ).fetchone()
    business = conn.execute(
        "SELECT * FROM builder_documents WHERE project_id=? AND document_key='business-site'", (project_id,)
    ).fetchone()
    if not customer or not business:
        return

    customer_schema = _json(customer["schema"], {})
    if customer_schema.get("migration_status") not in {"hybrid", "native"}:
        customer_schema.update({
            "adapter": "universal_native", "legacy_adapter": "customer_platform",
            "migration_status": "hybrid", "renderer_type": "hybrid_document",
            "legacy_fallback": "guest_home_legacy", "auth_context": "guest_or_customer",
            "metadata": {"title": "Home", "description": "Discover nearby stores, services and experiences."},
        })
        conn.execute("UPDATE builder_documents SET schema=?,schema_version=3,updated_at=? WHERE id=?",
                     (json.dumps(customer_schema), _now(), customer["id"]))
    if not conn.execute("SELECT 1 FROM builder_nodes WHERE document_id=? LIMIT 1", (customer["id"],)).fetchone():
        root = "official_customer_home_root"
        _insert_official_node(conn, customer["id"], root, "section", styles={"padding": "0", "background": "#f7f7f4"}, order=0,
                              metadata={"display_label": "Customer Home"})
        _insert_official_node(conn, customer["id"], "official_customer_nav", "navigation", parent_key=root, order=0,
                              props={"brand": "Zintriq", "links": "Home|/home\nPlaces|/venues\nAccount|account"},
                              styles={"padding": "18px 24px", "background": "#ffffff"})
        _insert_official_node(conn, customer["id"], "official_customer_hero", "hero", parent_key=root, order=1,
                              props={"eyebrow": "WELCOME", "title": "Discover stores and experiences near you",
                                     "body": "Explore stores, services and events in one place.", "image": ""},
                              styles={"padding": "64px 28px", "background": "#fff8d7", "borderRadius": "24px"},
                              responsive={"mobile": {"padding": "36px 18px", "borderRadius": "16px", "fontSize": "18px"}},
                              translations=_official_home_translations())
        _insert_official_node(conn, customer["id"], "official_customer_intro", "text", parent_key=root, order=2,
                              props={"body": "Scan in store, revisit saved places, or discover something new."},
                              styles={"padding": "12px 28px", "textAlign": "center"})
        _insert_official_node(conn, customer["id"], "official_store_grid", "store_grid", parent_key=root, order=3,
                              props={"title": "Featured stores", "limit": 6, "columns": 3, "show_description": True},
                              styles={"padding": "28px"}, responsive={"mobile": {"padding": "18px"}},
                              metadata={"capability": "commerce", "data_source": "commerce.stores"})
        _insert_official_node(conn, customer["id"], "official_booking", "booking", parent_key=root, order=4,
                              props={"title": "Book your visit"}, styles={"padding": "28px", "background": "#ffffff", "borderRadius": "18px"},
                              metadata={"capability": "booking", "backend": "qr_experience_runtime.public_create_booking"})
        _insert_official_node(conn, customer["id"], "official_feedback", "survey", parent_key=root, order=5,
                              props={"title": "Tell us what you think", "body": "Your feedback helps local businesses improve."},
                              styles={"padding": "28px", "background": "#ffffff", "borderRadius": "18px"},
                              metadata={"capability": "feedback", "manager_url": "/account"})
        _insert_official_node(conn, customer["id"], "official_customer_cta", "button", parent_key=root, order=6,
                              props={"label": "Browse all places", "variant": "primary"}, styles={"margin": "12px 28px 36px"})
        conn.execute(
            """INSERT OR IGNORE INTO builder_bindings
               (project_id,document_id,node_key,binding_key,source_type,source_config,transform,updated_at)
               VALUES (?,?,?,'items','domain',?,'{}',?)""",
            (project_id, customer["id"], "official_store_grid",
             json.dumps({"source_id": "commerce.stores", "query": {"status": "active", "limit": 6}}), _now()),
        )
        conn.execute(
            """INSERT OR IGNORE INTO builder_actions
               (project_id,document_id,node_key,action_key,event_type,action_type,configuration,sort_order,updated_at)
               VALUES (?,?,?,'official_browse_places','click','open_page',?,0,?)""",
            (project_id, customer["id"], "official_customer_cta", json.dumps({"path": "/venues"}), _now()),
        )

    business_schema = _json(business["schema"], {})
    if business_schema.get("migration_status") not in {"hybrid", "native"}:
        business_schema.update({
            "adapter": "universal_native", "legacy_adapter": "bos_shell",
            "migration_status": "hybrid", "renderer_type": "hybrid_document",
            "legacy_fallback": "bos.store", "auth_context": "business_workspace",
        })
        conn.execute("UPDATE builder_documents SET schema=?,schema_version=3,updated_at=? WHERE id=?",
                     (json.dumps(business_schema), _now(), business["id"]))
    if not conn.execute("SELECT 1 FROM builder_nodes WHERE document_id=? LIMIT 1", (business["id"],)).fetchone():
        shell = "official_business_shell"
        _insert_official_node(conn, business["id"], shell, "app_shell", order=0,
                              props={"brand": "Zintriq", "logo": "", "density": "comfortable", "accent": "#f3cf32"},
                              metadata={"display_label": "Business App Shell"})
        _insert_official_node(conn, business["id"], "official_business_nav", "navigation", parent_key=shell, slot="sidebar", order=0,
                              props={"brand": "Zintriq", "links": "Stores|/app/store\nTeam|/app/team\nSettings|/app/settings\nHelp|/business/help"})
        _insert_official_node(conn, business["id"], "official_business_header", "header", parent_key=shell, slot="header", order=1,
                              props={"title": "Stores", "subtitle": "Manage storefronts, customer QR and responses."})
        _insert_official_node(conn, business["id"], "official_store_manager", "app_module", parent_key=shell, slot="content", order=2,
                              props={"module_id": "commerce.store_manager", "title": "Store Manager", "height": 720},
                              metadata={"module_id": "commerce.store_manager", "migration_status": "adapted"})

    for document, surface_key, fallback in (
        (customer, "customer-site", "/home?legacy=1"),
        (business, "business-site", "/app/store?legacy=1"),
    ):
        conn.execute(
            """INSERT INTO builder_route_ownership
               (project_id,surface_id,document_id,route,renderer_type,migration_status,legacy_fallback,configuration,status,priority,updated_at)
               VALUES (?,?,?,?, 'hybrid_document','hybrid',?,?,'draft',100,?)
               ON CONFLICT(project_id,route) DO UPDATE SET surface_id=excluded.surface_id,document_id=excluded.document_id,
                 renderer_type=excluded.renderer_type,migration_status=excluded.migration_status,
                 legacy_fallback=excluded.legacy_fallback,configuration=excluded.configuration,updated_at=excluded.updated_at""",
            (project_id, surface_ids[surface_key], document["id"], document["route"], fallback,
             json.dumps({"fallback_on_error": True, "analytics_source": "hybrid"}), _now()),
        )


def sync_system_project(conn, workspace_id: int, created_by: int | None = None) -> int:
    """Attach the complete existing product to one Universal Builder project."""
    from bos.services.workspace import workspace_is_personal

    if workspace_is_personal(conn, workspace_id):
        raise ValueError("Personal workspaces do not attach the commerce system project")
    workspace = _workspace(conn, workspace_id)
    if not workspace:
        raise ValueError("Workspace not found")
    template = get_template(conn, "zintriq-system")
    manifest = _json(template["manifest"], {})
    legacy_id = str(workspace_id)
    existing = conn.execute(
        """SELECT * FROM builder_projects
           WHERE workspace_id=? AND legacy_source_type='workspace_system' AND legacy_source_id=?""",
        (workspace_id, legacy_id),
    ).fetchone()
    settings = {
        "runtime_adapter": "flask_legacy_bridge",
        "preserve_existing_routes": True,
        "customer_and_business_are_one_template": True,
        "template_entrypoints": {"business": "/app/store", "customer": "/home"},
        "capabilities": manifest.get("capabilities") or [],
    }
    if existing:
        project_id = int(existing["id"])
        conn.execute(
            """UPDATE builder_projects SET template_version=?, name=?, settings=?, enabled_capabilities=?, updated_at=? WHERE id=?""",
            (template["version"], f"{workspace['name']} — Business & Customer App", json.dumps(settings),
             json.dumps(manifest.get("required_capabilities") or []), _now(), project_id),
        )
    else:
        base_slug = f"{_slug(workspace['name'])}-system"
        slug = base_slug
        suffix = 2
        while conn.execute(
            "SELECT 1 FROM builder_projects WHERE workspace_id=? AND slug=?", (workspace_id, slug)
        ).fetchone():
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        cur = conn.execute(
            """INSERT INTO builder_projects
               (workspace_id, template_id, template_version, name, slug, kind, status,
                settings, enabled_capabilities, created_by, legacy_source_type, legacy_source_id, updated_at)
               VALUES (?, 'zintriq-system', ?, ?, ?, 'application', 'active', ?, ?, ?,
                       'workspace_system', ?, ?)""",
            (workspace_id, template["version"], f"{workspace['name']} — Business & Customer App", slug,
             json.dumps(settings), json.dumps(manifest.get("required_capabilities") or []), created_by, legacy_id, _now()),
        )
        project_id = int(cur.lastrowid)

    surface_ids = {}
    for order, surface in enumerate(manifest.get("surfaces") or []):
        conn.execute(
            """INSERT INTO builder_surfaces
               (project_id, surface_key, name, type, audience, base_path, settings, sort_order, updated_at)
               VALUES (?, ?, ?, 'legacy_web', ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, surface_key) DO UPDATE SET name=excluded.name,
                 audience=excluded.audience, base_path=excluded.base_path,
                 settings=excluded.settings, sort_order=excluded.sort_order, updated_at=excluded.updated_at""",
            (project_id, surface["id"], surface["name"], surface.get("audience", "public"),
             (surface.get("routes") or [""])[0], json.dumps({"routes": surface.get("routes") or []}), order, _now()),
        )
        surface_ids[surface["id"]] = conn.execute(
            "SELECT id FROM builder_surfaces WHERE project_id=? AND surface_key=?", (project_id, surface["id"])
        ).fetchone()["id"]

    for order, document in enumerate(manifest.get("documents") or []):
        schema = {
            "adapter": document.get("adapter"),
            "legacy_runtime": True,
            "preserve_existing_routes": True,
        }
        conn.execute(
            """INSERT INTO builder_documents
               (project_id, document_key, name, type, route, status, schema, sort_order, surface_id,
                legacy_source_type, legacy_source_id, updated_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, 'system_document', ?, ?)
               ON CONFLICT(project_id, document_key) DO UPDATE SET
                 name=excluded.name, type=excluded.type, route=excluded.route,
                 status='active', schema=excluded.schema, sort_order=excluded.sort_order,
                 surface_id=excluded.surface_id,
                 legacy_source_type=excluded.legacy_source_type,
                 legacy_source_id=excluded.legacy_source_id, updated_at=excluded.updated_at""",
            (project_id, document["key"], document["name"], document["type"],
             document.get("route", ""), json.dumps(schema), order,
             surface_ids.get(document["key"]) or surface_ids.get("business-site"), document["key"], _now()),
        )
    ensure_official_native_documents(conn, project_id, surface_ids)
    from universal_builder_creator import seed_official_creator_system
    seed_official_creator_system(conn, project_id)
    from universal_builder_marketplace import sync_official_component_packages
    sync_official_component_packages(conn, project_id)
    conn.execute(
        """INSERT INTO builder_deployments
           (project_id, environment, channel, status, adapter, public_url, configuration,
            deployed_at, updated_at)
           VALUES (?, 'production', 'web', 'active', 'flask_legacy_bridge', '/', ?, ?, ?)
           ON CONFLICT(project_id, environment, channel) DO UPDATE SET
             status='active',
             adapter=CASE WHEN builder_deployments.revision_id IS NULL THEN 'flask_legacy_bridge' ELSE builder_deployments.adapter END,
             public_url='/',
             configuration=CASE WHEN builder_deployments.revision_id IS NULL THEN excluded.configuration ELSE builder_deployments.configuration END,
             updated_at=excluded.updated_at""",
        (project_id, json.dumps({"preserve_existing_routes": True}), _now(), _now()),
    )
    from universal_builder_marketplace import sync_official_template_snapshot
    sync_official_template_snapshot(conn, project_id)
    return project_id


def create_blank_project(conn, workspace_id: int, name: str, created_by: int | None = None) -> int:
    base_slug = _slug(name or "Untitled Project")
    slug, suffix = base_slug, 2
    while conn.execute("SELECT 1 FROM builder_projects WHERE workspace_id=? AND slug=?", (workspace_id, slug)).fetchone():
        slug, suffix = f"{base_slug}-{suffix}", suffix + 1
    cur = conn.execute(
        """INSERT INTO builder_projects
           (workspace_id, name, slug, kind, status, description, schema_version,
            enabled_capabilities, settings, created_by, updated_at)
           VALUES (?, ?, ?, 'application', 'draft', '', 1, ?, '{}', ?, ?)""",
        (workspace_id, name or "Untitled Project", slug, json.dumps(["core", "navigation", "data"]), created_by, _now()),
    )
    project_id = int(cur.lastrowid)
    surface = conn.execute(
        """INSERT INTO builder_surfaces
           (project_id,surface_key,name,type,audience,base_path,settings,sort_order,updated_at)
           VALUES (?, 'public-web', 'Website', 'public_web', 'public', '/', '{}', 0, ?)""",
        (project_id, _now()),
    )
    surface_id = int(surface.lastrowid)
    document = conn.execute(
        """INSERT INTO builder_documents
           (project_id,surface_id,document_key,name,type,route,status,schema,sort_order,schema_version,updated_at)
           VALUES (?,?,'home','Home','page','/','active','{}',0,2,?)""",
        (project_id, surface_id, _now()),
    )
    document_id = int(document.lastrowid)
    conn.execute(
        """INSERT INTO builder_nodes
           (document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,
            responsive,translations,position,sort_order,visibility,permissions,metadata,schema_version,updated_at)
           VALUES (?,? ,NULL,'section','core/section','default','{}',?, '{}','{}','{}',0,'visible','[]','{}',2,?)""",
        (document_id, new_builder_key("section"), json.dumps({"padding": "32px"}), _now()),
    )
    conn.execute("UPDATE builder_projects SET default_surface_id=? WHERE id=?", (surface_id, project_id))
    from universal_builder_creator import seed_official_creator_system
    seed_official_creator_system(conn, project_id)
    return project_id


def new_builder_key(prefix: str = "node") -> str:
    from uuid import uuid4
    return f"{prefix}_{uuid4().hex[:16]}"


def create_project_from_template(
    conn, workspace_id: int, template_id: str, name: str, created_by: int | None = None
) -> int:
    if template_id == "zintriq-system":
        return sync_system_project(conn, workspace_id, created_by)
    template = get_template(conn, template_id)
    if not template:
        raise ValueError("Template not found")
    manifest = _json(template["manifest"], {})
    errors = validate_template_manifest(manifest)
    if errors:
        raise ValueError(f"Invalid template: {', '.join(errors)}")
    base_slug = _slug(name or template["name"])
    slug = base_slug
    suffix = 2
    while conn.execute(
        "SELECT 1 FROM builder_projects WHERE workspace_id=? AND slug=?", (workspace_id, slug)
    ).fetchone():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    cur = conn.execute(
        """INSERT INTO builder_projects
           (workspace_id, template_id, template_version, name, slug, kind, status,
            settings, created_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'draft', '{}', ?, ?)""",
        (workspace_id, template_id, template["version"], name or template["name"], slug,
         template["template_kind"], created_by, _now()),
    )
    project_id = int(cur.lastrowid)
    for order, document in enumerate(manifest.get("documents") or []):
        conn.execute(
            """INSERT INTO builder_documents
               (project_id, document_key, name, type, route, schema, sort_order, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, document["key"], document.get("name") or document["key"],
             document.get("type") or "page", document.get("route") or "",
             json.dumps({"adapter": document.get("adapter") or "native"}), order, _now()),
        )
    conn.execute(
        """INSERT INTO builder_deployments
           (project_id, environment, channel, status, adapter, configuration, updated_at)
           VALUES (?, 'production', 'web', 'draft', ?, '{}', ?)""",
        (project_id, (manifest.get("runtime") or {}).get("adapter") or "native", _now()),
    )
    return project_id


def _document_to_api(row) -> dict:
    return {
        "id": row["id"], "project_id": row["project_id"], "key": row["document_key"],
        "name": row["name"], "type": row["type"], "route": row["route"] or "",
        "status": row["status"], "schema": _json(row["schema"], {}),
        "order": row["sort_order"], "surface_id": row["surface_id"],
        "schema_version": row["schema_version"], "legacy_source_type": row["legacy_source_type"],
        "legacy_source_id": row["legacy_source_id"],
    }


def _node_to_api(row) -> dict:
    return {
        "id": row["id"], "document_id": row["document_id"], "key": row["node_key"],
        "parent_key": row["parent_key"], "component_type": row["component_type"],
        "component_reference": row["component_reference"] or f"core/{row['component_type']}",
        "slot": row["slot"] or "default", "props": _json(row["props"], {}),
        "styles": _json(row["styles"], {}), "responsive": _json(row["responsive"], {}),
        "translations": _json(row["translations"], {}), "position": _json(row["position"], {}),
        "order": row["sort_order"],
        "visibility": row["visibility"], "condition_id": row["condition_id"],
        "permissions": _json(row["permissions"], []), "metadata": _json(row["metadata"], {}),
        "schema_version": row["schema_version"],
    }


def builder_bootstrap(conn, project_id: int, document_id: int | None = None) -> dict:
    from universal_builder_creator import creator_payload
    project = conn.execute("SELECT * FROM builder_projects WHERE id=?", (project_id,)).fetchone()
    if not project:
        raise ValueError("Project not found")
    payload = project_to_api(conn, project, detail=True)
    active = None
    if document_id:
        active = conn.execute("SELECT * FROM builder_documents WHERE id=? AND project_id=?", (document_id, project_id)).fetchone()
    if not active:
        active = conn.execute(
            "SELECT * FROM builder_documents WHERE project_id=? AND status='active' ORDER BY sort_order,id LIMIT 1", (project_id,)
        ).fetchone()
    payload["active_document"] = _document_to_api(active) if active else None
    payload["nodes"] = [_node_to_api(row) for row in conn.execute(
        "SELECT * FROM builder_nodes WHERE document_id=? ORDER BY sort_order,id", (active["id"],)
    ).fetchall()] if active else []
    for table, key in (("builder_bindings", "bindings"), ("builder_actions", "actions")):
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE project_id=? AND (document_id IS NULL OR document_id=?) ORDER BY id",
            (project_id, active["id"] if active else -1),
        ).fetchall()
        payload[key] = [
            {field: (_json(value, {}) if field in {"source_config", "transform", "configuration"} else value) for field, value in dict(row).items()}
            for row in rows
        ]
    payload["conditions"] = [
        {**dict(row), "expression": _json(row["expression"], {})}
        for row in conn.execute("SELECT * FROM builder_conditions WHERE project_id=? ORDER BY id", (project_id,)).fetchall()
    ]
    payload["data_models"] = [
        {**dict(row), "schema": _json(row["schema"], {})}
        for row in conn.execute("SELECT * FROM builder_data_models WHERE project_id=? ORDER BY name", (project_id,)).fetchall()
    ]
    payload["installations"] = [dict(row) for row in conn.execute(
        "SELECT * FROM builder_package_installations WHERE project_id=? AND status='active'", (project_id,)
    ).fetchall()]
    payload["route_ownership"] = [
        {**dict(row), "configuration": _json(row["configuration"], {})}
        for row in conn.execute("SELECT * FROM builder_route_ownership WHERE project_id=? ORDER BY priority DESC,id", (project_id,)).fetchall()
    ]
    payload.update(creator_payload(conn, project_id))
    return payload


def project_to_api(conn, row, *, detail: bool = False) -> dict:
    result = {
        "id": row["id"], "workspace_id": row["workspace_id"], "template_id": row["template_id"],
        "template_version": row["template_version"], "name": row["name"], "slug": row["slug"],
        "kind": row["kind"], "status": row["status"], "description": row["description"] or "",
        "schema_version": row["schema_version"], "default_surface_id": row["default_surface_id"],
        "enabled_capabilities": _json(row["enabled_capabilities"], []),
        "theme_reference": row["theme_reference"] or "", "settings": _json(row["settings"], {}),
        "legacy_source_type": row["legacy_source_type"], "legacy_source_id": row["legacy_source_id"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "surface_count": conn.execute("SELECT COUNT(*) AS c FROM builder_surfaces WHERE project_id=?", (row["id"],)).fetchone()["c"],
        "document_count": conn.execute("SELECT COUNT(*) AS c FROM builder_documents WHERE project_id=? AND status='active'", (row["id"],)).fetchone()["c"],
    }
    if detail:
        result["surfaces"] = [
            {"id": item["id"], "key": item["surface_key"], "name": item["name"], "type": item["type"],
             "audience": item["audience"], "base_path": item["base_path"] or "",
             "settings": _json(item["settings"], {}), "order": item["sort_order"]}
            for item in conn.execute("SELECT * FROM builder_surfaces WHERE project_id=? ORDER BY sort_order,id", (row["id"],)).fetchall()
        ]
        result["documents"] = [
            _document_to_api(item) for item in conn.execute(
                "SELECT * FROM builder_documents WHERE project_id=? ORDER BY sort_order, id", (row["id"],)
            ).fetchall()
        ]
        result["deployments"] = [
            {
                "id": item["id"], "environment": item["environment"], "channel": item["channel"],
                "status": item["status"], "adapter": item["adapter"], "public_url": item["public_url"] or "",
                "revision_id": item["revision_id"],
                "configuration": _json(item["configuration"], {}), "deployed_at": item["deployed_at"],
            }
            for item in conn.execute("SELECT * FROM builder_deployments WHERE project_id=?", (row["id"],)).fetchall()
        ]
    return result


def capture_project_snapshot(conn, project_id: int) -> dict:
    from universal_builder_creator import capture_creator_resources
    project = conn.execute("SELECT * FROM builder_projects WHERE id=?", (project_id,)).fetchone()
    documents = conn.execute("SELECT * FROM builder_documents WHERE project_id=? ORDER BY sort_order, id", (project_id,)).fetchall()
    document_ids = [row["id"] for row in documents]
    nodes = []
    if document_ids:
        placeholders = ",".join("?" for _ in document_ids)
        nodes = [dict(row) for row in conn.execute(
            f"SELECT * FROM builder_nodes WHERE document_id IN ({placeholders}) ORDER BY document_id, sort_order, id",
            document_ids,
        ).fetchall()]
    snapshot = {
        "schema_version": 4,
        "project": project_to_api(conn, project),
        "surfaces": [dict(row) for row in conn.execute("SELECT * FROM builder_surfaces WHERE project_id=? ORDER BY sort_order,id", (project_id,)).fetchall()],
        "documents": [_document_to_api(row) for row in documents],
        "nodes": nodes,
        "bindings": [dict(row) for row in conn.execute("SELECT * FROM builder_bindings WHERE project_id=?", (project_id,)).fetchall()],
        "actions": [dict(row) for row in conn.execute("SELECT * FROM builder_actions WHERE project_id=?", (project_id,)).fetchall()],
        "data_models": [dict(row) for row in conn.execute("SELECT * FROM builder_data_models WHERE project_id=?", (project_id,)).fetchall()],
        # Publish must not embed preview records; live lists read the DB by surface.
        "data_records": [],
        "state": [dict(row) for row in conn.execute("SELECT * FROM builder_state_definitions WHERE project_id=?", (project_id,)).fetchall()],
        "conditions": [dict(row) for row in conn.execute("SELECT * FROM builder_conditions WHERE project_id=?", (project_id,)).fetchall()],
        "entry_points": [dict(row) for row in conn.execute("SELECT * FROM builder_entry_points WHERE project_id=?", (project_id,)).fetchall()],
        "route_ownership": [dict(row) for row in conn.execute("SELECT * FROM builder_route_ownership WHERE project_id=?", (project_id,)).fetchall()],
    }
    snapshot.update(capture_creator_resources(conn, project_id))
    return snapshot


def create_project_revision(conn, project_id: int, user_id: int | None, note: str = "") -> dict:
    number = conn.execute(
        "SELECT COALESCE(MAX(revision_number), 0) + 1 AS n FROM builder_project_revisions WHERE project_id=?",
        (project_id,),
    ).fetchone()["n"]
    cur = conn.execute(
        """INSERT INTO builder_project_revisions
           (project_id, revision_number, kind, snapshot, note, created_by)
           VALUES (?, ?, 'draft', ?, ?, ?)""",
        (project_id, number, json.dumps(capture_project_snapshot(conn, project_id)), note.strip(), user_id),
    )
    return {"id": cur.lastrowid, "project_id": project_id, "revision_number": number, "kind": "draft", "note": note.strip()}


def restore_project_snapshot(conn, project_id: int, snapshot: dict) -> None:
    """Materialize an immutable snapshot as the current draft.

    Revision and deployment rows are deliberately untouched. IDs used by the
    runtime are remapped while stable document/node keys are preserved.
    Callers pass an already-loaded snapshot dict; this function does not read
    a package or zip.
    """
    from builder_kernel.validate import validate_schema

    for item in snapshot.get("data_models") or []:
        schema = item.get("schema")
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError as error:
                raise ValueError("invalid model schema") from error
        result = validate_schema(schema)
        if not result.ok:
            raise ValueError("invalid model schema")
    snapshot_documents = snapshot.get("documents") or []
    snapshot_surfaces = snapshot.get("surfaces") or []
    surface_map: dict[int, int] = {}
    for item in snapshot_surfaces:
        conn.execute(
            """INSERT INTO builder_surfaces(project_id,surface_key,name,type,audience,base_path,settings,sort_order,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,surface_key) DO UPDATE SET name=excluded.name,type=excluded.type,
               audience=excluded.audience,base_path=excluded.base_path,settings=excluded.settings,sort_order=excluded.sort_order,updated_at=excluded.updated_at""",
            (project_id, item["surface_key"], item["name"], item.get("type", "public_web"), item.get("audience", "public"),
             item.get("base_path", ""), item.get("settings", "{}"), item.get("sort_order", 0), _now()),
        )
        current = conn.execute("SELECT id FROM builder_surfaces WHERE project_id=? AND surface_key=?", (project_id, item["surface_key"])).fetchone()
        surface_map[int(item["id"])] = int(current["id"])
    document_map: dict[int, int] = {}
    restored_keys = []
    for item in snapshot_documents:
        key = item.get("key", item.get("document_key")); restored_keys.append(key)
        conn.execute(
            """INSERT INTO builder_documents(project_id,surface_id,document_key,name,type,route,status,schema,sort_order,schema_version,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,document_key) DO UPDATE SET surface_id=excluded.surface_id,
               name=excluded.name,type=excluded.type,route=excluded.route,status=excluded.status,schema=excluded.schema,
               sort_order=excluded.sort_order,schema_version=excluded.schema_version,updated_at=excluded.updated_at""",
            (project_id, surface_map.get(item.get("surface_id")), key, item["name"], item.get("type", "page"), item.get("route", ""),
             item.get("status", "active"), json.dumps(item.get("schema") or {}), item.get("order", item.get("sort_order", 0)),
             item.get("schema_version", 2), _now()),
        )
        current = conn.execute("SELECT id FROM builder_documents WHERE project_id=? AND document_key=?", (project_id, key)).fetchone()
        document_map[int(item["id"])] = int(current["id"])
    if restored_keys:
        marks = ",".join("?" for _ in restored_keys)
        conn.execute(f"UPDATE builder_documents SET status='archived' WHERE project_id=? AND document_key NOT IN ({marks})", [project_id, *restored_keys])
    document_ids = [row["id"] for row in conn.execute("SELECT id FROM builder_documents WHERE project_id=?", (project_id,)).fetchall()]
    if document_ids:
        marks = ",".join("?" for _ in document_ids)
        conn.execute(f"DELETE FROM builder_nodes WHERE document_id IN ({marks})", document_ids)
    for table in ("builder_bindings", "builder_actions", "builder_data_records", "builder_data_models", "builder_state_definitions", "builder_conditions", "builder_entry_points"):
        conn.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
    condition_map = {}
    for item in snapshot.get("conditions") or []:
        cur = conn.execute(
            "INSERT INTO builder_conditions(project_id,condition_key,name,expression) VALUES (?,?,?,?)",
            (project_id, item["condition_key"], item["name"], item["expression"]),
        )
        condition_map[item.get("id")] = int(cur.lastrowid)
    for item in snapshot.get("nodes") or []:
        current_document = document_map.get(int(item["document_id"]))
        if not current_document: continue
        conn.execute(
            """INSERT INTO builder_nodes(document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,responsive,
               translations,position,sort_order,visibility,condition_id,permissions,metadata,schema_version,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (current_document, item["node_key"], item.get("parent_key"), item["component_type"], item.get("component_reference", ""),
             item.get("slot", "default"), item.get("props", "{}"), item.get("styles", "{}"), item.get("responsive", "{}"),
             item.get("translations", "{}"), item.get("position", "{}"), item.get("sort_order", 0), item.get("visibility", "visible"),
             condition_map.get(item.get("condition_id")), item.get("permissions", "[]"), item.get("metadata", "{}"), item.get("schema_version", 2), _now()),
        )
    for item in snapshot.get("bindings") or []:
        conn.execute(
            """INSERT INTO builder_bindings(project_id,document_id,node_key,binding_key,source_type,source_config,transform,updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (project_id, document_map.get(item.get("document_id")), item.get("node_key"), item["binding_key"], item["source_type"],
             item.get("source_config", "{}"), item.get("transform", "{}"), _now()),
        )
    for item in snapshot.get("actions") or []:
        conn.execute(
            """INSERT INTO builder_actions(project_id,document_id,node_key,action_key,event_type,action_type,configuration,sort_order,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (project_id, document_map.get(item.get("document_id")), item.get("node_key"), item["action_key"], item["event_type"],
             item["action_type"], item.get("configuration", "{}"), item.get("sort_order", 0), _now()),
        )
    for item in snapshot.get("data_models") or []:
        conn.execute("INSERT INTO builder_data_models(project_id,model_key,name,schema,adapter,updated_at) VALUES (?,?,?,?,?,?)",
                     (project_id, item["model_key"], item["name"], item["schema"], item.get("adapter", "native"), _now()))
    for item in snapshot.get("data_records") or []:
        conn.execute(
            """INSERT INTO builder_data_records(project_id,model_key,record_key,data,status,surface,updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                project_id,
                item["model_key"],
                item["record_key"],
                item["data"],
                item.get("status", "active"),
                item.get("surface") or "preview",
                _now(),
            ),
        )
    for item in snapshot.get("state") or []:
        conn.execute("INSERT INTO builder_state_definitions(project_id,state_key,scope,initial_value,value_schema) VALUES (?,?,?,?,?)",
                     (project_id, item["state_key"], item.get("scope", "project"), item.get("initial_value", "null"), item.get("value_schema", "{}")))
    from universal_builder_creator import restore_creator_resources
    restore_creator_resources(conn, project_id, snapshot, document_map)
    project_data = snapshot.get("project") or {}
    conn.execute(
        """UPDATE builder_projects SET name=?,description=?,settings=?,enabled_capabilities=?,theme_reference=?,status='draft',updated_at=? WHERE id=?""",
        (project_data.get("name", "Project"), project_data.get("description", ""), json.dumps(project_data.get("settings") or {}),
         json.dumps(project_data.get("enabled_capabilities") or []), project_data.get("theme_reference", ""), _now(), project_id),
    )


def ensure_studio_workspace_for_user(user_id: int) -> bool:
    """Guarantee a workspace membership so /studio can list projects.

    Returns True when the user had no active membership before this call.
    """
    from app import db
    from bos.services.organization import ensure_default_organization
    from bos.services.workspace import ensure_default_workspace

    owner_id = int(user_id)
    with db() as conn:
        before = conn.execute(
            "SELECT COUNT(*) AS c FROM workspace_members WHERE user_id=? AND status='active'",
            (owner_id,),
        ).fetchone()["c"]
        ensure_default_organization(conn, owner_id)
        workspace = ensure_default_workspace(conn, owner_id)
        workspace_id = int(workspace["id"])
        exists = conn.execute(
            "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
            (workspace_id, owner_id),
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO workspace_members (workspace_id, user_id, role, status, joined_at)
                   VALUES (?, ?, 'owner', 'active', CURRENT_TIMESTAMP)""",
                (workspace_id, owner_id),
            )
        from flask import has_request_context, session

        if has_request_context() and not session.get("active_workspace_id"):
            session["active_workspace_id"] = workspace_id
        return int(before) == 0


def register_universal_builder_core(app) -> None:
    from flask import Response, abort, jsonify, redirect, render_template, request, session
    from app import csrf_token, current_user, db, login_required
    from universal_component_registry import new_node_key, registry_payload
    from bos.permissions import has_permission
    from universal_builder_capabilities import capability_payload
    from universal_builder_migration import validate_route_ownership
    from universal_builder_modules import (
        app_module_payload, collect_snapshot_domain_sources, data_source_payload, load_domain_data,
    )
    from universal_builder_packages import package_summary, validate_package_manifest
    from universal_builder_runtime import published_snapshot, render_document
    from universal_builder_creator import (
        create_definition_from_subtree, creator_payload, definition_usage,
        detach_instance, insert_instance, keyify, row_api, validate_creator_resources,
    )

    def runtime_domain_data(conn, snapshot: dict, workspace_id: int, *, public: bool) -> dict:
        return {
            source_id: load_domain_data(conn, source_id, workspace_id=workspace_id, query=query, public=public)
            for source_id, query in collect_snapshot_domain_sources(snapshot).items()
        }

    def context(permission: str = "builder.read"):
        user = current_user()
        workspace_id = session.get("active_workspace_id")
        if not user or not workspace_id:
            abort(400)
        with db() as conn:
            allowed = has_permission(conn, int(user["id"]), int(workspace_id), permission)
            if not allowed:
                fallback = "workspace.read" if permission == "builder.read" else "workspace.update"
                allowed = has_permission(conn, int(user["id"]), int(workspace_id), fallback)
        if not allowed:
            abort(403)
        return int(user["id"]), int(workspace_id)

    def owned_project(conn, project_id: int, workspace_id: int):
        row = conn.execute(
            "SELECT * FROM builder_projects WHERE id=? AND workspace_id=?", (project_id, workspace_id)
        ).fetchone()
        if not row:
            abort(404)
        return row

    @app.get("/app/builder")
    @login_required
    def universal_builder_home():
        from app import workspace_snapshot
        user = current_user()
        owner_id = user["id"]
        ws_id = session.get("active_workspace_id")
        needs_setup = False
        with db() as conn:
            if ws_id:
                ok = conn.execute(
                    "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=? AND status='active'",
                    (int(ws_id), owner_id),
                ).fetchone()
                if not ok:
                    ws_id = None
            if not ws_id:
                row = conn.execute(
                    """SELECT w.id FROM workspaces w
                       JOIN workspace_members wm ON wm.workspace_id = w.id
                       WHERE wm.user_id=? AND wm.status='active'
                       ORDER BY w.id LIMIT 1""",
                    (owner_id,),
                ).fetchone()
                if not row:
                    from bos.services.organization import ensure_default_organization
                    from bos.services.workspace import ensure_default_workspace
                    ensure_default_organization(conn, owner_id)
                    ws = ensure_default_workspace(conn, owner_id)
                    ws_id = int(ws["id"])
                    exists = conn.execute(
                        "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
                        (ws_id, owner_id),
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            """INSERT INTO workspace_members (workspace_id, user_id, role, status, joined_at)
                               VALUES (?, ?, 'owner', 'active', CURRENT_TIMESTAMP)""",
                            (ws_id, owner_id),
                        )
                    from workspace_platform import WORKSPACE_MODULES
                    for mod in WORKSPACE_MODULES:
                        conn.execute(
                            "INSERT OR IGNORE INTO workspace_modules (workspace_id, module_id, enabled) VALUES (?, ?, 1)",
                            (ws_id, mod),
                        )
                    needs_setup = True
                else:
                    ws_id = int(row["id"])
            session["active_workspace_id"] = ws_id
        workspace = workspace_snapshot(owner_id)
        return render_template(
            "workspace_dashboard.html",
            page_title="Workspace",
            workspace=workspace,
            needs_workspace_setup=needs_setup,
        )

    @app.get("/app/builder/<int:project_id>")
    @login_required
    def universal_builder_editor(project_id: int):
        _, workspace_id = context()
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
        return render_template("builder/editor.html", page_title=project["name"], project_id=project_id)

    @app.get("/api/builder-core/schema")
    @login_required
    def api_builder_core_schema():
        context()
        return jsonify({
            "schema_version": 4,
            "hierarchy": ["project", "surface", "document", "node"],
            "creator_hierarchy": ["component_definition", "component_instance", "variant", "slot"],
            "extensions": ["binding", "action", "interaction", "state", "condition", "data_model", "design_token", "project_variable", "workflow", "deployment", "revision", "package"],
            "document_types": ["site", "page", "application", "commerce", "dashboard", "workflow", "data_model", "runtime", "builder"],
            "deployment_channels": ["web", "domain", "qr", "embed", "portal", "api"],
        })

    @app.get("/api/builder-core/components")
    @login_required
    def api_builder_core_components():
        context()
        return jsonify(registry_payload())

    @app.get("/api/builder-core/capabilities")
    @login_required
    def api_builder_core_capabilities():
        context()
        return jsonify({"schema_version": 1, "capabilities": capability_payload()})

    @app.get("/api/builder-core/app-modules")
    @login_required
    def api_builder_core_app_modules():
        context()
        return jsonify({"schema_version": 1, "modules": app_module_payload()})

    @app.get("/api/builder-core/data-sources")
    @login_required
    def api_builder_core_data_sources():
        context()
        return jsonify({"schema_version": 1, "sources": data_source_payload()})

    @app.get("/api/builder-core/projects/<int:project_id>/domain-data/<path:source_id>")
    @login_required
    def api_builder_core_domain_data(project_id: int, source_id: str):
        user_id, workspace_id = context()
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            spec = data_source_payload(source_id)
            if not spec:
                abort(404)
            permission = spec.get("permission")
            if permission and not has_permission(conn, user_id, workspace_id, permission):
                abort(403)
            query = {key: value for key, value in request.args.items() if key in {"status", "discoverable", "store_id", "limit"}}
            if "limit" in query:
                query["limit"] = request.args.get("limit", type=int)
            if "store_id" in query:
                query["store_id"] = request.args.get("store_id", type=int)
            if "discoverable" in query:
                query["discoverable"] = request.args.get("discoverable", "").lower() in {"1", "true", "yes"}
            return jsonify({"source": spec, "records": load_domain_data(conn, source_id, workspace_id=workspace_id, query=query)})

    @app.get("/api/builder-core/packages")
    @login_required
    def api_builder_core_packages():
        context()
        with db() as conn:
            rows = conn.execute("SELECT * FROM builder_packages WHERE status='active' ORDER BY trust_level='official' DESC,id").fetchall()
            return jsonify({"packages": [{**package_summary(_json(row["manifest"], {})), "trust_level": row["trust_level"]} for row in rows]})

    @app.get("/api/builder-core/templates")
    @app.get("/api/community/templates")
    @login_required
    def api_builder_core_templates():
        context()
        with db() as conn:
            rows = conn.execute("SELECT * FROM builder_templates WHERE status='active' ORDER BY visibility='official' DESC, name").fetchall()
            return jsonify({"templates": [template_to_api(row) for row in rows]})

    @app.get("/api/builder-core/templates/<template_id>")
    @login_required
    def api_builder_core_template_detail(template_id: str):
        context()
        with db() as conn:
            row = get_template(conn, template_id)
            if not row:
                abort(404)
            return jsonify(template_to_api(row))

    @app.get("/api/builder-core/projects")
    @login_required
    def api_builder_core_projects():
        user_id, workspace_id = context()
        with db() as conn:
            from bos.services.workspace import workspace_is_personal

            if not workspace_is_personal(conn, workspace_id):
                sync_system_project(conn, workspace_id, user_id)
            rows = conn.execute(
                "SELECT * FROM builder_projects WHERE workspace_id=? ORDER BY updated_at DESC, id DESC",
                (workspace_id,),
            ).fetchall()
            return jsonify({"projects": [project_to_api(conn, row) for row in rows]})

    @app.post("/api/builder-core/projects")
    @login_required
    def api_builder_core_project_create():
        user_id, workspace_id = context("builder.create")
        data = request.get_json(silent=True) or {}
        template_id = str(data.get("template_id") or "").strip()
        with db() as conn:
            try:
                if template_id:
                    project_id = create_project_from_template(
                        conn, workspace_id, template_id, str(data.get("name") or "").strip(), user_id
                    )
                else:
                    project_id = create_blank_project(conn, workspace_id, str(data.get("name") or "Untitled Project").strip(), user_id)
            except ValueError as error:
                return jsonify({"error": str(error)}), 400
            row = conn.execute("SELECT * FROM builder_projects WHERE id=?", (project_id,)).fetchone()
            return jsonify(project_to_api(conn, row, detail=True)), 201

    @app.post("/api/builder-core/projects/from-system")
    @login_required
    def api_builder_core_sync_system():
        user_id, workspace_id = context("builder.update")
        with db() as conn:
            try:
                project_id = sync_system_project(conn, workspace_id, user_id)
            except ValueError as error:
                return jsonify({"error": str(error)}), 400
            row = conn.execute("SELECT * FROM builder_projects WHERE id=?", (project_id,)).fetchone()
            return jsonify(project_to_api(conn, row, detail=True)), 201

    @app.get("/api/builder-core/projects/<int:project_id>")
    @login_required
    def api_builder_core_project_detail(project_id: int):
        _, workspace_id = context()
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM builder_projects WHERE id=? AND workspace_id=?", (project_id, workspace_id)
            ).fetchone()
            if not row:
                abort(404)
            return jsonify(project_to_api(conn, row, detail=True))

    @app.get("/api/builder-core/projects/<int:project_id>/bootstrap")
    @login_required
    def api_builder_core_bootstrap(project_id: int):
        _, workspace_id = context()
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            payload = builder_bootstrap(conn, project_id, request.args.get("document_id", type=int))
            payload["registry"] = registry_payload()
            payload["capability_registry"] = capability_payload()
            payload["app_module_registry"] = app_module_payload()
            payload["data_source_registry"] = data_source_payload()
            return jsonify(payload)

    @app.patch("/api/builder-core/projects/<int:project_id>")
    @login_required
    def api_builder_core_project_update(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            row = owned_project(conn, project_id, workspace_id)
            updates, values = [], []
            for field in ("name", "description", "theme_reference"):
                if field in data:
                    updates.append(f"{field}=?"); values.append(str(data[field]))
            if "settings" in data:
                settings = _json(row["settings"], {}); settings.update(data["settings"] or {})
                updates.append("settings=?"); values.append(json.dumps(settings))
            if "enabled_capabilities" in data:
                requested = list(dict.fromkeys(data["enabled_capabilities"] or []))
                from universal_builder_capabilities import validate_capabilities
                errors = validate_capabilities(requested)
                if errors:
                    return jsonify({"error": errors[0], "issues": errors}), 400
                updates.append("enabled_capabilities=?"); values.append(json.dumps(requested))
            if updates:
                updates.append("updated_at=?"); values.extend([_now(), project_id])
                conn.execute(f"UPDATE builder_projects SET {', '.join(updates)} WHERE id=?", values)
            updated = conn.execute("SELECT * FROM builder_projects WHERE id=?", (project_id,)).fetchone()
            return jsonify(project_to_api(conn, updated, detail=True))

    @app.post("/api/builder-core/projects/<int:project_id>/revisions")
    @login_required
    def api_builder_core_revision(project_id: int):
        user_id, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM builder_projects WHERE id=? AND workspace_id=?", (project_id, workspace_id)
            ).fetchone()
            if not row:
                abort(404)
            return jsonify(create_project_revision(conn, project_id, user_id, str(data.get("note") or "Saved draft"))), 201

    @app.get("/api/builder-core/projects/<int:project_id>/revisions")
    @login_required
    def api_builder_core_revisions(project_id: int):
        _, workspace_id = context()
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            rows = conn.execute(
                """SELECT id,project_id,revision_number,kind,note,created_by,created_at
                   FROM builder_project_revisions WHERE project_id=? ORDER BY revision_number DESC""", (project_id,),
            ).fetchall()
            return jsonify({"revisions": [dict(row) for row in rows]})

    @app.post("/api/builder-core/projects/<int:project_id>/revisions/<int:revision_id>/rollback")
    @login_required
    def api_builder_core_rollback(project_id: int, revision_id: int):
        _, workspace_id = context("builder.publish")
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            revision = conn.execute(
                "SELECT * FROM builder_project_revisions WHERE id=? AND project_id=?", (revision_id, project_id)
            ).fetchone()
            if not revision:
                abort(404)
            deployment = conn.execute(
                "SELECT * FROM builder_deployments WHERE project_id=? AND environment='production' AND channel='web'",
                (project_id,),
            ).fetchone()
            if not deployment:
                return jsonify({"error": "Project has not been published"}), 409
            conn.execute(
                """UPDATE builder_deployments SET revision_id=?,status='active',adapter='universal_native',
                   public_url=?,deployed_at=?,updated_at=? WHERE id=?""",
                (revision_id, f"/build/{project['slug']}", _now(), _now(), deployment["id"]),
            )
            return jsonify({"ok": True, "revision_id": revision_id, "revision_number": revision["revision_number"],
                            "public_url": f"/build/{project['slug']}"})

    @app.post("/api/builder-core/projects/<int:project_id>/revisions/<int:revision_id>/restore")
    @login_required
    def api_builder_core_restore_draft(project_id: int, revision_id: int):
        user_id, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            revision = conn.execute(
                "SELECT * FROM builder_project_revisions WHERE id=? AND project_id=?", (revision_id, project_id)
            ).fetchone()
            if not revision: abort(404)
            safety = create_project_revision(conn, project_id, user_id, "Automatic backup before restore")
            try:
                restore_project_snapshot(conn, project_id, _json(revision["snapshot"], {}))
            except ValueError as error:
                return jsonify({"ok": False, "error": {"code": "validation_error", "message": str(error), "fields": []}}), 400
            restored = create_project_revision(conn, project_id, user_id, f"Restored version {revision['revision_number']}")
            return jsonify({"ok": True, "restored_revision_id": restored["id"], "backup_revision_id": safety["id"],
                            "source_revision_id": revision_id, "status": "draft"}), 201

    @app.post("/api/builder-core/projects/<int:project_id>/surfaces")
    @login_required
    def api_builder_core_surface_create(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        key = _slug(str(data.get("key") or data.get("name") or "surface"))
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            cur = conn.execute(
                """INSERT INTO builder_surfaces
                   (project_id,surface_key,name,type,audience,base_path,settings,sort_order,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (project_id, key, str(data.get("name") or "Surface"), str(data.get("type") or "public_web"),
                 str(data.get("audience") or "public"), str(data.get("base_path") or ""),
                 json.dumps(data.get("settings") or {}), int(data.get("order") or 0), _now()),
            )
            surface_id = int(cur.lastrowid)
            conn.execute("UPDATE builder_projects SET default_surface_id=COALESCE(default_surface_id,?),updated_at=? WHERE id=?", (surface_id, _now(), project_id))
            return jsonify({"id": surface_id, "project_id": project_id, "key": key}), 201

    @app.patch("/api/builder-core/projects/<int:project_id>/surfaces/<int:surface_id>")
    @login_required
    def api_builder_core_surface_update(project_id: int, surface_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            surface = conn.execute("SELECT * FROM builder_surfaces WHERE id=? AND project_id=?", (surface_id, project_id)).fetchone()
            if not surface: abort(404)
            values = [str(data.get("name", surface["name"])), str(data.get("base_path", surface["base_path"] or "")),
                      json.dumps(data.get("settings", _json(surface["settings"], {}))), _now(), surface_id]
            conn.execute("UPDATE builder_surfaces SET name=?,base_path=?,settings=?,updated_at=? WHERE id=?", values)
            return jsonify({"ok": True, "id": surface_id})

    @app.post("/api/builder-core/projects/<int:project_id>/documents")
    @login_required
    def api_builder_core_document_create(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        key = _slug(str(data.get("key") or data.get("name") or "page"))
        from builder_kernel.ids import IdentifierError, check_document_key

        try:
            check_document_key(key)
        except IdentifierError:
            return jsonify({"error": "That page key is reserved or invalid."}), 400
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            surface_id = data.get("surface_id")
            if surface_id and not conn.execute("SELECT 1 FROM builder_surfaces WHERE id=? AND project_id=?", (surface_id, project_id)).fetchone():
                abort(400)
            route, route_error = _validate_document_route(conn, project_id, data.get("route") or f"/{key}", surface_id=surface_id)
            if route_error:
                return jsonify(route_error[0]), route_error[1]
            cur = conn.execute(
                """INSERT INTO builder_documents
                   (project_id,surface_id,document_key,name,type,route,status,schema,sort_order,schema_version,updated_at)
                   VALUES (?,?,?,?,?,?,'active',?,?,2,?)""",
                (project_id, surface_id, key, str(data.get("name") or "Page"), str(data.get("type") or "page"),
                 route, json.dumps(data.get("schema") or {}), int(data.get("order") or 0), _now()),
            )
            row = conn.execute("SELECT * FROM builder_documents WHERE id=?", (cur.lastrowid,)).fetchone()
            return jsonify(_document_to_api(row)), 201

    @app.patch("/api/builder-core/projects/<int:project_id>/documents/<int:document_id>")
    @login_required
    def api_builder_core_document_update(project_id: int, document_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            row = conn.execute("SELECT * FROM builder_documents WHERE id=? AND project_id=?", (document_id, project_id)).fetchone()
            if not row: abort(404)
            route, route_error = _validate_document_route(
                conn, project_id, data.get("route", row["route"] or ""), exclude_document_id=document_id, allow_empty=True,
                surface_id=data.get("surface_id", row["surface_id"]),
            )
            if route_error:
                return jsonify(route_error[0]), route_error[1]
            conn.execute(
                "UPDATE builder_documents SET name=?,route=?,surface_id=?,status=?,updated_at=? WHERE id=?",
                (str(data.get("name", row["name"])), route,
                 data.get("surface_id", row["surface_id"]), str(data.get("status", row["status"])), _now(), document_id),
            )
            return jsonify(_document_to_api(conn.execute("SELECT * FROM builder_documents WHERE id=?", (document_id,)).fetchone()))

    @app.post("/api/builder-core/projects/<int:project_id>/documents/<int:document_id>/duplicate")
    @login_required
    def api_builder_core_document_duplicate(project_id: int, document_id: int):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            source = conn.execute("SELECT * FROM builder_documents WHERE id=? AND project_id=?", (document_id, project_id)).fetchone()
            if not source: abort(404)
            key = f"{source['document_key']}-copy"; suffix = 2
            while conn.execute("SELECT 1 FROM builder_documents WHERE project_id=? AND document_key=?", (project_id, key)).fetchone():
                key = f"{source['document_key']}-copy-{suffix}"; suffix += 1
            new_route = _unique_document_route(conn, project_id, source["route"] or f"/{key}", surface_id=source["surface_id"])
            cur = conn.execute(
                """INSERT INTO builder_documents(project_id,surface_id,document_key,name,type,route,status,schema,sort_order,schema_version,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id, source["surface_id"], key, f"{source['name']} copy", source["type"], new_route, "active",
                 source["schema"], source["sort_order"] + 1, source["schema_version"], _now()),
            )
            new_document_id = int(cur.lastrowid)
            nodes = conn.execute("SELECT * FROM builder_nodes WHERE document_id=? ORDER BY id", (document_id,)).fetchall()
            key_map = {row["node_key"]: new_builder_key(row["component_type"]) for row in nodes}
            for node in nodes:
                conn.execute(
                    """INSERT INTO builder_nodes(document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,responsive,
                       translations,position,sort_order,visibility,condition_id,permissions,metadata,schema_version,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (new_document_id, key_map[node["node_key"]], key_map.get(node["parent_key"]), node["component_type"], node["component_reference"],
                     node["slot"], node["props"], node["styles"], node["responsive"], node["translations"], node["position"], node["sort_order"], node["visibility"],
                     node["condition_id"], node["permissions"], node["metadata"], node["schema_version"], _now()),
                )
            return jsonify(_document_to_api(conn.execute("SELECT * FROM builder_documents WHERE id=?", (new_document_id,)).fetchone())), 201

    @app.delete("/api/builder-core/projects/<int:project_id>/documents/<int:document_id>")
    @login_required
    def api_builder_core_document_archive(project_id: int, document_id: int):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            count = conn.execute("SELECT COUNT(*) AS c FROM builder_documents WHERE project_id=? AND status='active'", (project_id,)).fetchone()["c"]
            if count <= 1: return jsonify({"error": "A project needs at least one page"}), 409
            conn.execute("UPDATE builder_documents SET status='archived',updated_at=? WHERE id=? AND project_id=?", (_now(), document_id, project_id))
            return jsonify({"ok": True})

    @app.post("/api/builder-core/projects/<int:project_id>/nodes")
    @login_required
    def api_builder_core_node_create(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        document_id = int(data.get("document_id") or 0)
        component_type = str(data.get("component_type") or "text")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            if not conn.execute("SELECT 1 FROM builder_documents WHERE id=? AND project_id=?", (document_id, project_id)).fetchone():
                abort(400)
            registry = registry_payload()["components"]
            if component_type not in registry:
                return jsonify({"error": "Unknown component_type"}), 400
            key = str(data.get("key") or new_node_key())
            parent_key = data.get("parent_key")
            if parent_key:
                parent = conn.execute("SELECT * FROM builder_nodes WHERE document_id=? AND node_key=?", (document_id, parent_key)).fetchone()
                if not parent: return jsonify({"error": "parent_key not found"}), 400
                parent_spec = registry.get(parent["component_type"], {})
                child_spec = registry[component_type]
                if "*" not in (parent_spec.get("allowed_children") or []) and component_type not in (parent_spec.get("allowed_children") or []):
                    return jsonify({"error": "Component is not allowed inside that parent"}), 400
                if parent["component_type"] not in (child_spec.get("allowed_parents") or []):
                    return jsonify({"error": "Parent type is not allowed for this component"}), 400
            props = dict(registry[component_type].get("defaults") or {})
            props.update(data.get("props") or {})
            cur = conn.execute(
                """INSERT INTO builder_nodes
                   (document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,responsive,translations,position,
                    sort_order,visibility,condition_id,permissions,metadata,schema_version,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (document_id, key, parent_key, component_type, registry[component_type]["id"], str(data.get("slot") or "default"),
                 json.dumps(props), json.dumps(data.get("styles") or {}), json.dumps(data.get("responsive") or {}),
                 json.dumps(data.get("translations") or {}), json.dumps(data.get("position") or {}),
                 int(data.get("order") or 0), str(data.get("visibility") or "visible"),
                 data.get("condition_id"), json.dumps(data.get("permissions") or []), json.dumps(data.get("metadata") or {}), 2, _now()),
            )
            return jsonify({"id": int(cur.lastrowid), "key": key, "document_id": document_id, "component_type": component_type, "props": props}), 201

    @app.patch("/api/builder-core/projects/<int:project_id>/nodes/<node_key>")
    @login_required
    def api_builder_core_node_update(project_id: int, node_key: str):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        allowed = {"parent_key", "slot", "visibility", "condition_id", "sort_order"}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            node = conn.execute("""SELECT n.* FROM builder_nodes n JOIN builder_documents d ON d.id=n.document_id
                                   WHERE d.project_id=? AND n.node_key=?""", (project_id, node_key)).fetchone()
            if not node:
                abort(404)
            if "parent_key" in data:
                parent_key = data.get("parent_key")
                if parent_key:
                    parent = conn.execute("SELECT * FROM builder_nodes WHERE document_id=? AND node_key=?", (node["document_id"], parent_key)).fetchone()
                    if not parent: return jsonify({"error": "parent_key not found"}), 400
                    cursor = parent
                    while cursor:
                        if cursor["node_key"] == node_key: return jsonify({"error": "A component cannot contain itself"}), 400
                        cursor = conn.execute("SELECT * FROM builder_nodes WHERE document_id=? AND node_key=?", (node["document_id"], cursor["parent_key"])).fetchone() if cursor["parent_key"] else None
                    registry = registry_payload()["components"]
                    parent_spec, child_spec = registry.get(parent["component_type"], {}), registry.get(node["component_type"], {})
                    if "*" not in (parent_spec.get("allowed_children") or []) and node["component_type"] not in (parent_spec.get("allowed_children") or []):
                        return jsonify({"error": "Component is not allowed inside that parent"}), 400
                    if parent["component_type"] not in (child_spec.get("allowed_parents") or []):
                        return jsonify({"error": "Parent type is not allowed for this component"}), 400
            if data.get("condition_id") and not conn.execute("SELECT 1 FROM builder_conditions WHERE id=? AND project_id=?", (data["condition_id"], project_id)).fetchone():
                return jsonify({"error": "condition_id not found"}), 400
            updates, values = [], []
            for field in allowed:
                request_key = "order" if field == "sort_order" else field
                if request_key in data:
                    updates.append(f"{field}=?"); values.append(data[request_key])
            for field in ("props", "styles", "responsive", "translations", "permissions", "metadata", "position"):
                if field in data:
                    updates.append(f"{field}=?"); values.append(json.dumps(data[field]))
            if updates:
                updates.append("updated_at=?"); values.extend([_now(), node["id"]])
                conn.execute(f"UPDATE builder_nodes SET {', '.join(updates)} WHERE id=?", values)
            return jsonify({"ok": True, "key": node_key})

    @app.delete("/api/builder-core/projects/<int:project_id>/nodes/<node_key>")
    @login_required
    def api_builder_core_node_delete(project_id: int, node_key: str):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            node = conn.execute("""SELECT n.* FROM builder_nodes n JOIN builder_documents d ON d.id=n.document_id
                                   WHERE d.project_id=? AND n.node_key=?""", (project_id, node_key)).fetchone()
            if not node: abort(404)
            descendants, frontier = [], [node_key]
            while frontier:
                current = frontier.pop(); descendants.append(current)
                frontier.extend(row["node_key"] for row in conn.execute(
                    "SELECT node_key FROM builder_nodes WHERE document_id=? AND parent_key=?", (node["document_id"], current)
                ).fetchall())
            marks = ",".join("?" for _ in descendants)
            conn.execute(f"DELETE FROM builder_bindings WHERE project_id=? AND node_key IN ({marks})", [project_id, *descendants])
            conn.execute(f"DELETE FROM builder_actions WHERE project_id=? AND node_key IN ({marks})", [project_id, *descendants])
            conn.execute(f"DELETE FROM builder_component_instances WHERE project_id=? AND node_key IN ({marks})", [project_id, *descendants])
            conn.execute(f"DELETE FROM builder_nodes WHERE document_id=? AND node_key IN ({marks})", [node["document_id"], *descendants])
            return jsonify({"ok": True, "deleted": descendants})

    @app.post("/api/builder-core/projects/<int:project_id>/nodes/<node_key>/duplicate")
    @login_required
    def api_builder_core_node_duplicate(project_id: int, node_key: str):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            node = conn.execute("""SELECT n.* FROM builder_nodes n JOIN builder_documents d ON d.id=n.document_id
                                   WHERE d.project_id=? AND n.node_key=?""", (project_id, node_key)).fetchone()
            if not node: abort(404)
            subtree, frontier = [], [node]
            while frontier:
                current = frontier.pop(0); subtree.append(current)
                frontier.extend(conn.execute(
                    "SELECT * FROM builder_nodes WHERE document_id=? AND parent_key=? ORDER BY sort_order,id",
                    (node["document_id"], current["node_key"]),
                ).fetchall())
            key_map = {item["node_key"]: new_builder_key(item["component_type"]) for item in subtree}
            for item in subtree:
                conn.execute(
                    """INSERT INTO builder_nodes(document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,responsive,
                       translations,position,sort_order,visibility,condition_id,permissions,metadata,schema_version,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item["document_id"], key_map[item["node_key"]], key_map.get(item["parent_key"], item["parent_key"]), item["component_type"],
                     item["component_reference"], item["slot"], item["props"], item["styles"], item["responsive"], item["translations"],
                     item["position"],
                     item["sort_order"] + (1 if item["node_key"] == node_key else 0), item["visibility"], item["condition_id"],
                     item["permissions"], item["metadata"], item["schema_version"], _now()),
                )
                for binding in conn.execute("SELECT * FROM builder_bindings WHERE project_id=? AND node_key=?", (project_id, item["node_key"])).fetchall():
                    conn.execute(
                        """INSERT INTO builder_bindings(project_id,document_id,node_key,binding_key,source_type,source_config,transform,updated_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (project_id, binding["document_id"], key_map[item["node_key"]], binding["binding_key"], binding["source_type"], binding["source_config"], binding["transform"], _now()),
                    )
                for action in conn.execute("SELECT * FROM builder_actions WHERE project_id=? AND node_key=?", (project_id, item["node_key"])).fetchall():
                    conn.execute(
                        """INSERT INTO builder_actions(project_id,document_id,node_key,action_key,event_type,action_type,configuration,sort_order,updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (project_id, action["document_id"], key_map[item["node_key"]], new_builder_key("act"), action["event_type"], action["action_type"], action["configuration"], action["sort_order"], _now()),
                    )
                instance = conn.execute("SELECT * FROM builder_component_instances WHERE project_id=? AND document_id=? AND node_key=?", (project_id, item["document_id"], item["node_key"])).fetchone()
                if instance:
                    conn.execute("""INSERT INTO builder_component_instances(project_id,document_id,node_key,component_definition_id,variant,overrides,slot_content,bindings,responsive,updated_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?)""",(project_id,item["document_id"],key_map[item["node_key"]],instance["component_definition_id"],instance["variant"],instance["overrides"],instance["slot_content"],instance["bindings"],instance["responsive"],_now()))
            new_key = key_map[node_key]
            return jsonify({"ok": True, "key": new_key}), 201

    @app.post("/api/builder-core/projects/<int:project_id>/bindings")
    @login_required
    def api_builder_core_binding_upsert(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute(
                """INSERT INTO builder_bindings
                   (project_id,document_id,node_key,binding_key,source_type,source_config,transform,updated_at)
                   VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(project_id,document_id,node_key,binding_key) DO UPDATE SET
                   source_type=excluded.source_type,source_config=excluded.source_config,transform=excluded.transform,updated_at=excluded.updated_at""",
                (project_id, data.get("document_id"), data.get("node_key"), str(data.get("binding_key") or "text"),
                 str(data.get("source_type") or "literal"), json.dumps(data.get("source_config") or {}),
                 json.dumps(data.get("transform") or {}), _now()),
            )
            return jsonify({"ok": True}), 201

    @app.delete("/api/builder-core/projects/<int:project_id>/bindings/<int:binding_id>")
    @login_required
    def api_builder_core_binding_delete(project_id: int, binding_id: int):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute("DELETE FROM builder_bindings WHERE id=? AND project_id=?", (binding_id, project_id))
            return jsonify({"ok": True})

    @app.post("/api/builder-core/projects/<int:project_id>/actions")
    @login_required
    def api_builder_core_action_upsert(project_id: int):
        _, workspace_id = context("builder.update")
        from builder_components import normalize_builder_action

        data = request.get_json(silent=True) or {}
        try:
            normalized = normalize_builder_action({
                "key": data.get("key"),
                "action_type": data.get("action_type"),
                "type": data.get("action_type"),
                "configuration": data.get("configuration") or {},
                "order": data.get("order") or 0,
            })
        except ValueError:
            return jsonify({"ok": False, "error": {"code": "unknown_action", "message": "Unknown action.", "fields": [{"path": "action_type", "code": "unknown"}]}}), 400
        action_key = str(data.get("key") or normalized["key"])
        event_type = str(data.get("event_type") or "on_click")
        if event_type == "submit":
            event_type = "on_submit"
        if event_type == "click":
            event_type = "on_click"
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute(
                """INSERT INTO builder_actions
                   (project_id,document_id,node_key,action_key,event_type,action_type,configuration,sort_order,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,action_key) DO UPDATE SET
                   document_id=excluded.document_id,node_key=excluded.node_key,event_type=excluded.event_type,
                   action_type=excluded.action_type,configuration=excluded.configuration,sort_order=excluded.sort_order,updated_at=excluded.updated_at""",
                (project_id, data.get("document_id"), data.get("node_key"), action_key, event_type,
                 normalized["type"], json.dumps(data.get("configuration") or {}), int(data.get("order") or 0), _now()),
            )
            return jsonify({"ok": True, "key": action_key, "action_type": normalized["type"]}), 201

    @app.delete("/api/builder-core/projects/<int:project_id>/actions/<int:action_id>")
    @login_required
    def api_builder_core_action_delete(project_id: int, action_id: int):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute("DELETE FROM builder_actions WHERE id=? AND project_id=?", (action_id, project_id))
            return jsonify({"ok": True})

    @app.post("/api/builder-core/projects/<int:project_id>/data-models")
    @login_required
    def api_builder_core_data_model(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        model_key = _slug(str(data.get("key") or data.get("name") or "model")).replace("-", "_")
        schema = data.get("schema") or {"type": "object", "properties": {}}
        from builder_kernel.validate import validate_schema

        schema_result = validate_schema(schema)
        if not schema_result.ok:
            return jsonify(schema_result.to_dict()), schema_result.http_status()
        adapter = str(data.get("adapter") or "native")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute(
                """INSERT INTO builder_data_models(project_id,model_key,name,schema,adapter,updated_at)
                   VALUES (?,?,?,?,?,?) ON CONFLICT(project_id,model_key) DO UPDATE SET
                   name=excluded.name,schema=excluded.schema,adapter=excluded.adapter,updated_at=excluded.updated_at""",
                (project_id, model_key, str(data.get("name") or model_key), json.dumps(schema), adapter, _now()),
            )
            return jsonify({"ok": True, "key": model_key, "schema": schema}), 201

    @app.patch("/api/builder-core/projects/<int:project_id>/data-models/<model_key>")
    @login_required
    def api_builder_core_data_model_update(project_id: int, model_key: str):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            row = conn.execute("SELECT * FROM builder_data_models WHERE project_id=? AND model_key=?", (project_id, model_key)).fetchone()
            if not row: abort(404)
            schema = data.get("schema", _json(row["schema"], {}))
            from builder_kernel.validate import validate_schema

            schema_result = validate_schema(schema)
            if not schema_result.ok:
                return jsonify(schema_result.to_dict()), schema_result.http_status()
            conn.execute("UPDATE builder_data_models SET name=?,schema=?,updated_at=? WHERE id=?", (
                str(data.get("name", row["name"])), json.dumps(schema), _now(), row["id"]
            ))
            return jsonify({"ok": True})

    @app.delete("/api/builder-core/projects/<int:project_id>/data-models/<model_key>")
    @login_required
    def api_builder_core_data_model_delete(project_id: int, model_key: str):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            row = conn.execute("SELECT id FROM builder_data_models WHERE project_id=? AND model_key=?", (project_id, model_key)).fetchone()
            if not row: abort(404)
            conn.execute("DELETE FROM builder_data_records WHERE project_id=? AND model_key=?", (project_id, model_key))
            conn.execute("DELETE FROM builder_data_models WHERE id=?", (row["id"],))
            return jsonify({"ok": True})

    @app.get("/api/builder-core/projects/<int:project_id>/data-models/<model_key>/records")
    @login_required
    def api_builder_core_data_records(project_id: int, model_key: str):
        _, workspace_id = context()
        from builder_kernel.records import SURFACE_PREVIEW

        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            rows = conn.execute(
                """SELECT * FROM builder_data_records
                   WHERE project_id=? AND model_key=? AND surface=? AND status!='archived'
                   ORDER BY id DESC LIMIT 200""",
                (project_id, model_key, SURFACE_PREVIEW),
            ).fetchall()
            return jsonify({"records": [{**dict(row), "data": _json(row["data"], {})} for row in rows]})

    @app.post("/api/builder-core/projects/<int:project_id>/data-models/<model_key>/records")
    @login_required
    def api_builder_core_data_record(project_id: int, model_key: str):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        from builder_kernel.ids import new_record_key
        from builder_kernel.records import SURFACE_PREVIEW
        from builder_kernel.validate import prepare_record_write

        record_key = str(data.get("key") or new_record_key())
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            model = conn.execute("SELECT * FROM builder_data_models WHERE project_id=? AND model_key=?", (project_id, model_key)).fetchone()
            if not model:
                abort(404)
            write = prepare_record_write(model["adapter"], _json(model["schema"], {}), data.get("data") or {})
            if not write.ok:
                return jsonify(write.to_dict()), write.http_status()
            conn.execute(
                """INSERT INTO builder_data_records(project_id,model_key,record_key,data,status,surface,updated_at)
                   VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id,model_key,record_key) DO UPDATE SET
                   data=excluded.data,status=excluded.status,surface=excluded.surface,updated_at=excluded.updated_at""",
                (
                    project_id,
                    model_key,
                    record_key,
                    json.dumps(data.get("data") or {}),
                    str(data.get("status") or "active"),
                    SURFACE_PREVIEW,
                    _now(),
                ),
            )
            return jsonify({"ok": True, "key": record_key}), 201

    @app.patch("/api/builder-core/projects/<int:project_id>/data-models/<model_key>/records/<record_key>")
    @login_required
    def api_builder_core_data_record_update(project_id: int, model_key: str, record_key: str):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        from builder_kernel.records import SURFACE_PREVIEW

        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            row = conn.execute(
                """SELECT * FROM builder_data_records
                   WHERE project_id=? AND model_key=? AND record_key=? AND surface=?""",
                (project_id, model_key, record_key, SURFACE_PREVIEW),
            ).fetchone()
            if not row: abort(404)
            model = conn.execute("SELECT * FROM builder_data_models WHERE project_id=? AND model_key=?", (project_id, model_key)).fetchone()
            if not model:
                abort(404)
            from builder_kernel.validate import prepare_record_write

            new_data = data.get("data", _json(row["data"], {}))
            write = prepare_record_write(model["adapter"], _json(model["schema"], {}), new_data)
            if not write.ok:
                return jsonify(write.to_dict()), write.http_status()
            conn.execute("UPDATE builder_data_records SET data=?,status=?,updated_at=? WHERE id=?", (
                json.dumps(new_data), str(data.get("status", row["status"])), _now(), row["id"]
            ))
            return jsonify({"ok": True})

    @app.delete("/api/builder-core/projects/<int:project_id>/data-models/<model_key>/records/<record_key>")
    @login_required
    def api_builder_core_data_record_delete(project_id: int, model_key: str, record_key: str):
        _, workspace_id = context("builder.update")
        from builder_kernel.records import SURFACE_PREVIEW

        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute(
                """UPDATE builder_data_records SET status='archived',updated_at=?
                   WHERE project_id=? AND model_key=? AND record_key=? AND surface=?""",
                (_now(), project_id, model_key, record_key, SURFACE_PREVIEW),
            )
            return jsonify({"ok": True})

    @app.post("/api/builder-core/projects/<int:project_id>/state")
    @login_required
    def api_builder_core_state(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        state_key = str(data.get("key") or "state")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute(
                """INSERT INTO builder_state_definitions(project_id,state_key,scope,initial_value,value_schema)
                   VALUES (?,?,?,?,?) ON CONFLICT(project_id,state_key) DO UPDATE SET scope=excluded.scope,
                   initial_value=excluded.initial_value,value_schema=excluded.value_schema""",
                (project_id, state_key, str(data.get("scope") or "project"), json.dumps(data.get("initial_value")), json.dumps(data.get("schema") or {})),
            )
            return jsonify({"ok": True, "key": state_key}), 201

    @app.post("/api/builder-core/projects/<int:project_id>/conditions")
    @login_required
    def api_builder_core_condition(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        condition_key = str(data.get("key") or new_node_key("cond"))
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute(
                """INSERT INTO builder_conditions(project_id,condition_key,name,expression)
                   VALUES (?,?,?,?) ON CONFLICT(project_id,condition_key) DO UPDATE SET name=excluded.name,expression=excluded.expression""",
                (project_id, condition_key, str(data.get("name") or "Condition"), json.dumps(data.get("expression") or {})),
            )
            row = conn.execute("SELECT id FROM builder_conditions WHERE project_id=? AND condition_key=?", (project_id, condition_key)).fetchone()
            return jsonify({"ok": True, "id": row["id"], "key": condition_key}), 201

    @app.post("/api/builder-core/projects/<int:project_id>/packages/<package_id>/install")
    @login_required
    def api_builder_core_package_install(project_id: int, package_id: str):
        user_id, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            from universal_builder_marketplace import install_package
            # Compatibility for the pre-Marketplace official-package endpoint.
            # Community packages never receive this trusted shortcut.
            legacy_package = conn.execute("SELECT * FROM builder_packages WHERE id=?", (package_id,)).fetchone()
            granted = data.get("granted_permissions") or []
            if legacy_package and legacy_package["trust_level"] == "official" and not data.get("granted_permissions"):
                legacy_manifest = _json(legacy_package["manifest"], {})
                enabled = list(dict.fromkeys([*_json(project["enabled_capabilities"], []), *(legacy_manifest.get("required_capabilities") or [])]))
                conn.execute("UPDATE builder_projects SET enabled_capabilities=?,updated_at=? WHERE id=?", (json.dumps(enabled), _now(), project_id))
                project = owned_project(conn, project_id, workspace_id)
                granted = legacy_manifest.get("permissions") or []
            try:
                result = install_package(
                    conn, project=project, package_id=package_id, user_id=user_id,
                    granted_permissions=granted, version=data.get("version"),
                )
            except PermissionError as exc:
                return jsonify({"error": str(exc)}), 403
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 409
            return jsonify(result), 201

    @app.post("/api/builder-core/projects/<int:project_id>/entry-points")
    @login_required
    def api_builder_core_entry_point(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        entry_type, entry_key = str(data.get("type") or "qr"), str(data.get("key") or "").lower().strip()
        if not entry_key:
            return jsonify({"error": "key is required"}), 400
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute(
                """INSERT INTO builder_entry_points(project_id,surface_id,document_id,entry_type,entry_key,configuration,status,updated_at)
                   VALUES (?,?,?,?,?,?,'active',?) ON CONFLICT(entry_type,entry_key) DO UPDATE SET
                   project_id=excluded.project_id,surface_id=excluded.surface_id,document_id=excluded.document_id,
                   configuration=excluded.configuration,status='active',updated_at=excluded.updated_at""",
                (project_id, data.get("surface_id"), data.get("document_id"), entry_type, entry_key,
                 json.dumps(data.get("configuration") or {}), _now()),
            )
            return jsonify({"ok": True, "type": entry_type, "key": entry_key}), 201

    @app.get("/api/builder-core/projects/<int:project_id>/route-ownership")
    @login_required
    def api_builder_core_route_ownership(project_id: int):
        _, workspace_id = context()
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            rows = conn.execute("SELECT * FROM builder_route_ownership WHERE project_id=? ORDER BY priority DESC,id", (project_id,)).fetchall()
            return jsonify({"routes": [{**dict(row), "configuration": _json(row["configuration"], {})} for row in rows]})

    @app.post("/api/builder-core/projects/<int:project_id>/route-ownership/<int:ownership_id>/fallback")
    @login_required
    def api_builder_core_route_fallback(project_id: int, ownership_id: int):
        _, workspace_id = context("builder.publish")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            row = conn.execute("SELECT * FROM builder_route_ownership WHERE id=? AND project_id=?", (ownership_id, project_id)).fetchone()
            if not row: abort(404)
            conn.execute("UPDATE builder_route_ownership SET status='fallback',updated_at=? WHERE id=?", (_now(), ownership_id))
            return jsonify({"ok": True, "route": row["route"], "fallback": row["legacy_fallback"], "status": "fallback"})

    @app.post("/api/builder-core/projects/<int:project_id>/route-ownership/<int:ownership_id>/activate")
    @login_required
    def api_builder_core_route_activate(project_id: int, ownership_id: int):
        _, workspace_id = context("builder.publish")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            row = conn.execute("SELECT * FROM builder_route_ownership WHERE id=? AND project_id=?", (ownership_id, project_id)).fetchone()
            if not row: abort(404)
            issues = validate_route_ownership(conn, project_id)
            errors = [item for item in issues if item["level"] == "error"]
            if errors: return jsonify({"error": errors[0]["message"], "issues": issues}), 400
            conn.execute("UPDATE builder_route_ownership SET status='active',updated_at=? WHERE id=?", (_now(), ownership_id))
            return jsonify({"ok": True, "route": row["route"], "status": "active"})

    @app.get("/api/builder-core/projects/<int:project_id>/creator")
    @login_required
    def api_builder_creator(project_id: int):
        _, workspace_id = context()
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            return jsonify(creator_payload(conn, project_id))

    @app.post("/api/builder-core/projects/<int:project_id>/components/from-node")
    @login_required
    def api_builder_component_from_node(project_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            try:
                result = create_definition_from_subtree(conn, project_id, int(data.get("document_id") or 0),
                                                        str(data.get("node_key") or ""), str(data.get("name") or "Reusable Component").strip(),
                                                        str(data.get("description") or "").strip())
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify(result), 201

    @app.patch("/api/builder-core/projects/<int:project_id>/components/<int:definition_id>")
    @login_required
    def api_builder_component_update(project_id: int, definition_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        allowed = {"name", "description", "root_structure", "property_schema", "slots", "variants", "default_variant", "data_inputs", "events", "token_dependencies", "metadata"}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            row = conn.execute("SELECT * FROM builder_component_definitions WHERE id=? AND project_id=?", (definition_id, project_id)).fetchone()
            if not row: abort(404)
            updates, values = [], []
            for field in allowed:
                if field in data:
                    updates.append(f"{field}=?"); values.append(json.dumps(data[field]) if field not in {"name", "description", "default_variant"} else data[field])
            if updates:
                updates.extend(["version=version+1", "updated_at=?"]); values.extend([_now(), definition_id])
                conn.execute(f"UPDATE builder_component_definitions SET {', '.join(updates)} WHERE id=?", values)
            return jsonify(row_api(conn.execute("SELECT * FROM builder_component_definitions WHERE id=?", (definition_id,)).fetchone()))

    @app.delete("/api/builder-core/projects/<int:project_id>/components/<int:definition_id>")
    @login_required
    def api_builder_component_delete(project_id: int, definition_id: int):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            usage = definition_usage(conn, project_id, definition_id)
            if usage: return jsonify({"error": "Component is still used", "usage": usage}), 409
            conn.execute("DELETE FROM builder_component_definitions WHERE id=? AND project_id=?", (definition_id, project_id))
            return jsonify({"ok": True})

    @app.get("/api/builder-core/projects/<int:project_id>/components/<int:definition_id>/usage")
    @login_required
    def api_builder_component_usage(project_id: int, definition_id: int):
        _, workspace_id = context()
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            return jsonify({"usage": definition_usage(conn, project_id, definition_id)})

    @app.post("/api/builder-core/projects/<int:project_id>/components/<int:definition_id>/instances")
    @login_required
    def api_builder_component_instance_create(project_id: int, definition_id: int):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            try:
                result = insert_instance(conn, project_id, int(data.get("document_id") or 0), definition_id,
                                         data.get("parent_key"), int(data.get("order") or 0), data.get("variant"))
            except ValueError as exc: return jsonify({"error": str(exc)}), 400
            return jsonify(result), 201

    @app.patch("/api/builder-core/projects/<int:project_id>/instances/<node_key>")
    @login_required
    def api_builder_component_instance_update(project_id: int, node_key: str):
        _, workspace_id = context("builder.update")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            row = conn.execute("SELECT * FROM builder_component_instances WHERE project_id=? AND node_key=?", (project_id, node_key)).fetchone()
            if not row: abort(404)
            definition = conn.execute("SELECT * FROM builder_component_definitions WHERE id=?", (row["component_definition_id"],)).fetchone()
            variants = _json(definition["variants"], {})
            variant = data.get("variant", row["variant"])
            if variant not in variants: return jsonify({"error": "Unknown component variant"}), 400
            overrides = data.get("overrides", _json(row["overrides"], {}))
            exposed = (_json(definition["property_schema"], {}).get("properties") or {})
            if any(key not in exposed for key in overrides): return jsonify({"error": "Override is not exposed by the component"}), 400
            conn.execute("UPDATE builder_component_instances SET variant=?,overrides=?,slot_content=?,bindings=?,responsive=?,updated_at=? WHERE id=?",
                         (variant,json.dumps(overrides),json.dumps(data.get("slot_content",_json(row["slot_content"],{}))),json.dumps(data.get("bindings",_json(row["bindings"],{}))),json.dumps(data.get("responsive",_json(row["responsive"],{}))),_now(),row["id"]))
            conn.execute("UPDATE builder_nodes SET props=?,updated_at=? WHERE document_id=? AND node_key=?", (json.dumps({"definition_id":row["component_definition_id"],"variant":variant}),_now(),row["document_id"],node_key))
            return jsonify(row_api(conn.execute("SELECT * FROM builder_component_instances WHERE id=?",(row["id"],)).fetchone()))

    @app.post("/api/builder-core/projects/<int:project_id>/instances/<node_key>/detach")
    @login_required
    def api_builder_component_instance_detach(project_id: int, node_key: str):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            try: return jsonify(detach_instance(conn, project_id, node_key))
            except ValueError as exc: return jsonify({"error": str(exc)}), 400

    @app.post("/api/builder-core/projects/<int:project_id>/design-tokens")
    @login_required
    def api_builder_token_save(project_id: int):
        _, workspace_id = context("builder.update"); data = request.get_json(silent=True) or {}
        token_key = keyify(data.get("key") or data.get("name"), "token")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute("""INSERT INTO builder_design_tokens(project_id,token_key,name,category,group_name,values_json,description,updated_at) VALUES (?,?,?,?,?,?,?,?)
              ON CONFLICT(project_id,token_key) DO UPDATE SET name=excluded.name,category=excluded.category,group_name=excluded.group_name,values_json=excluded.values_json,description=excluded.description,updated_at=excluded.updated_at""",
              (project_id,token_key,data.get("name") or token_key,data.get("category") or "color",data.get("group") or "",json.dumps(data.get("values") or {"default":data.get("value") or ""}),data.get("description") or "",_now()))
            return jsonify({"ok":True,"key":token_key}), 201

    @app.delete("/api/builder-core/projects/<int:project_id>/design-tokens/<path:token_key>")
    @login_required
    def api_builder_token_delete(project_id: int, token_key: str):
        _, workspace_id = context("builder.update")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            usage = conn.execute("SELECT COUNT(*) c FROM builder_component_definitions WHERE project_id=? AND root_structure LIKE ?",(project_id,f"%token:{token_key}%")).fetchone()["c"]
            if usage: return jsonify({"error":"Token is still referenced","usage_count":usage}),409
            conn.execute("DELETE FROM builder_design_tokens WHERE project_id=? AND token_key=?",(project_id,token_key)); return jsonify({"ok":True})

    @app.post("/api/builder-core/projects/<int:project_id>/variables")
    @login_required
    def api_builder_variable_save(project_id: int):
        _, workspace_id = context("builder.update"); data=request.get_json(silent=True) or {}; variable_key=keyify(data.get("key") or data.get("name"),"variable")
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            conn.execute("""INSERT INTO builder_project_variables(project_id,variable_key,name,value_json,value_type,group_name,updated_at) VALUES (?,?,?,?,?,?,?)
              ON CONFLICT(project_id,variable_key) DO UPDATE SET name=excluded.name,value_json=excluded.value_json,value_type=excluded.value_type,group_name=excluded.group_name,updated_at=excluded.updated_at""",
              (project_id,variable_key,data.get("name") or variable_key,json.dumps(data.get("value")),data.get("type") or "string",data.get("group") or "",_now()))
            return jsonify({"ok":True,"key":variable_key}),201

    @app.post("/api/builder-core/projects/<int:project_id>/interactions")
    @login_required
    def api_builder_interaction_save(project_id: int):
        _, workspace_id=context("builder.update"); data=request.get_json(silent=True) or {}; interaction_key=str(data.get("key") or new_builder_key("interaction"))
        allowed={"entrance","hover","press","focus","selected","scroll_reveal","state_transition"}
        if data.get("trigger") not in allowed: return jsonify({"error":"Unsupported interaction trigger"}),400
        with db() as conn:
            owned_project(conn,project_id,workspace_id)
            conn.execute("""INSERT INTO builder_interactions(project_id,document_id,node_key,interaction_key,trigger_type,interaction_type,configuration,updated_at) VALUES (?,?,?,?,?,?,?,?)
              ON CONFLICT(project_id,interaction_key) DO UPDATE SET trigger_type=excluded.trigger_type,interaction_type=excluded.interaction_type,configuration=excluded.configuration,updated_at=excluded.updated_at""",
              (project_id,data.get("document_id"),data.get("node_key"),interaction_key,data["trigger"],data.get("type") or "fade",json.dumps(data.get("configuration") or {}),_now()))
            return jsonify({"ok":True,"key":interaction_key}),201

    @app.get("/api/builder-core/projects/<int:project_id>/preview/<document_key>")
    @login_required
    def api_builder_core_preview(project_id: int, document_key: str):
        _, workspace_id = context()
        from builder_kernel.records import SURFACE_PREVIEW, load_live_collections

        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            snapshot = capture_project_snapshot(conn, project_id)
            live = load_live_collections(
                conn,
                project_id=project_id,
                snapshot=snapshot,
                surface=SURFACE_PREVIEW,
            )
            output = render_document(
                snapshot, document_key, csrf=csrf_token(), locale=request.args.get("lang", "en"),
                domain_data=runtime_domain_data(conn, snapshot, workspace_id, public=False),
                invoke_url=f"/api/builder-core/projects/{project_id}/runtime/invoke",
                collections=live,
            )
            if output is None:
                abort(404)
            from builder_kernel.csp import BUILD_CSP

            response = Response(output, mimetype="text/html")
            response.headers["Content-Security-Policy"] = BUILD_CSP
            return response

    @app.post("/api/builder-core/projects/<int:project_id>/runtime/invoke")
    @login_required
    def api_builder_core_runtime_invoke(project_id: int):
        user_id, workspace_id = context("builder.update")
        from builder_kernel.invoke import invoke_snapshot_action

        body = request.get_json(silent=True) or {}
        document_key = str(body.get("document_key") or "")
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            snapshot = capture_project_snapshot(conn, project_id)
            status, payload = invoke_snapshot_action(
                conn,
                snapshot=snapshot,
                project=dict(project),
                document_key=document_key,
                body=body,
                user_id=user_id,
                public=False,
            )
            return jsonify(payload), status

    @app.post("/api/builder-core/projects/<int:project_id>/publish")
    @login_required
    def api_builder_core_publish(project_id: int):
        user_id, workspace_id = context("builder.publish")
        data = request.get_json(silent=True) or {}
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            migration_issues = validate_route_ownership(conn, project_id)
            creator_issues = validate_creator_resources(capture_project_snapshot(conn, project_id))
            migration_issues.extend(creator_issues)
            errors = [issue for issue in migration_issues if issue["level"] == "error"]
            if errors:
                return jsonify({"error": errors[0]["message"], "issues": migration_issues}), 400
            revision = create_project_revision(conn, project_id, user_id, str(data.get("note") or "Published"))
            conn.execute("UPDATE builder_project_revisions SET kind='published' WHERE id=?", (revision["id"],))
            from bos.services.workspace import workspace_is_personal

            is_hybrid = (
                project["legacy_source_type"] == "workspace_system"
                and not workspace_is_personal(conn, workspace_id)
            )
            public_url = "/" if is_hybrid else f"/build/{project['slug']}"
            adapter = "hybrid_strangler" if is_hybrid else "universal_native"
            conn.execute(
                """INSERT INTO builder_deployments(project_id,environment,channel,status,adapter,public_url,revision_id,configuration,deployed_at,updated_at)
                   VALUES (?,'production','web','active',?,?,?,?, ?,?)
                   ON CONFLICT(project_id,environment,channel) DO UPDATE SET status='active',adapter=excluded.adapter,
                   public_url=excluded.public_url,revision_id=excluded.revision_id,configuration=excluded.configuration,
                   deployed_at=excluded.deployed_at,updated_at=excluded.updated_at""",
                (project_id, adapter, public_url, revision["id"],
                 json.dumps({"immutable_snapshot": True, "legacy_fallback": is_hybrid}), _now(), _now()),
            )
            if is_hybrid:
                conn.execute("UPDATE builder_route_ownership SET status='active',updated_at=? WHERE project_id=? AND migration_status IN ('hybrid','native')", (_now(), project_id))
            conn.execute("UPDATE builder_projects SET status='published',updated_at=? WHERE id=?", (_now(), project_id))
            revision["kind"] = "published"; revision["public_url"] = public_url
            return jsonify(revision), 201

    @app.get("/app/builder-module/<path:module_id>")
    @login_required
    def universal_builder_module_host(module_id: str):
        user_id, workspace_id = context()
        project_id = request.args.get("project_id", type=int)
        module = app_module_payload(module_id)
        if not module or not project_id:
            abort(404)
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            enabled = set(_json(project["enabled_capabilities"], []))
            if any(item not in enabled for item in module.get("required_capabilities", [])):
                abort(403)
            if module.get("permission") and not has_permission(conn, user_id, workspace_id, module["permission"]):
                abort(403)
        if module_id == "commerce.store_manager":
            from app import workspace_snapshot
            return render_template(
                "bos/store_module.html", module_id="store", page_title="Store Manager",
                page_subtitle="Managed through the existing Commerce capability.",
                workspace=workspace_snapshot(user_id), workspace_mode="all", builder_module_mode=True,
            )
        return render_template(
            "builder/module_placeholder.html", page_title=module["name"], module=module,
            manager_url=module.get("manager_url", "/app/builder"),
        )

    @app.get("/build/<project_slug>/<document_key>")
    def universal_builder_public(project_slug: str, document_key: str):
        from builder_kernel.limits import PUBLIC_LIST_DEFAULT_LIMIT, PUBLIC_LIST_MAX_LIMIT
        from builder_kernel.records import SURFACE_PUBLISHED, load_live_collections

        # ?all=1 must never expand enumeration past the hard max.
        try:
            limit = int(request.args.get("limit") or PUBLIC_LIST_DEFAULT_LIMIT)
        except (TypeError, ValueError):
            limit = PUBLIC_LIST_DEFAULT_LIMIT
        limit = max(1, min(PUBLIC_LIST_MAX_LIMIT, limit))
        try:
            offset = max(0, int(request.args.get("offset") or 0))
        except (TypeError, ValueError):
            offset = 0
        with db() as conn:
            project, snapshot = published_snapshot(conn, project_slug)
            if not snapshot:
                abort(404)
            from work_urls import work_dict, work_from_store

            store = conn.execute(
                "SELECT id, slug FROM stores WHERE workspace_id=? ORDER BY id LIMIT 1",
                (project["workspace_id"],),
            ).fetchone()
            work = work_from_store(store) if store else work_dict(kind="build", slug=project_slug)
            live = load_live_collections(
                conn,
                project_id=int(project["id"]),
                snapshot=snapshot,
                surface=SURFACE_PUBLISHED,
                limit=limit,
                offset=offset,
            )
            # Anonymous live list only includes public_read models.
            from builder_kernel.records import model_allows_public_read

            filtered = {}
            for model in snapshot.get("data_models") or []:
                key = str(model.get("model_key") or "")
                if not key:
                    continue
                if model_allows_public_read(model.get("schema")):
                    filtered[key] = live.get(key, [])
                else:
                    filtered[key] = []
            output = render_document(
                snapshot, document_key, csrf=csrf_token(), locale=request.args.get("lang", "en"),
                domain_data=runtime_domain_data(conn, snapshot, int(project["workspace_id"]), public=True),
                work=work,
                invoke_url=f"/build/{project_slug}/{document_key}/runtime/invoke",
                collections=filtered,
            )
            if output is None:
                abort(404)
            from builder_kernel.csp import BUILD_CSP

            response = Response(output, mimetype="text/html")
            response.headers["Content-Security-Policy"] = BUILD_CSP
            return response

    @app.get("/build/<project_slug>/records/<model_key>/<record_key>")
    def universal_builder_public_record(project_slug: str, model_key: str, record_key: str):
        from builder_kernel.records import (
            SURFACE_PUBLISHED,
            get_live_record,
            model_allows_public_read,
        )
        from universal_builder_runtime import render_record_detail

        not_found = Response("Not found.", status=404, mimetype="text/plain")
        with db() as conn:
            project, snapshot = published_snapshot(conn, project_slug)
            if not snapshot:
                return not_found
            model = next(
                (item for item in (snapshot.get("data_models") or []) if item.get("model_key") == model_key),
                None,
            )
            # Anonymous: missing model, no public_read, or missing record → same 404.
            if not model or not model_allows_public_read(model.get("schema")):
                return not_found
            record = get_live_record(
                conn,
                project_id=int(project["id"]),
                model_key=model_key,
                record_key=record_key,
                surface=SURFACE_PUBLISHED,
            )
            if not record:
                return not_found
            return Response(
                render_record_detail(
                    project_slug=project_slug,
                    model_key=model_key,
                    record=record,
                    model_name=str(model.get("name") or model_key),
                ),
                mimetype="text/html",
            )

    @app.post("/build/<project_slug>/<document_key>/runtime/invoke")
    def universal_builder_public_invoke(project_slug: str, document_key: str):
        from builder_kernel.invoke import (
            check_public_invoke_size,
            error_body,
            honeypot_triggered,
            http_status_for,
            invoke_snapshot_action,
        )
        from builder_kernel.rate_limit import anonymous_write_allowed, get_rate_limiter

        raw = request.get_data(cache=True)
        body = request.get_json(silent=True) or {}
        oversized = check_public_invoke_size(request.content_length, raw, body)
        if oversized:
            return jsonify(oversized), 413
        if honeypot_triggered(body):
            return ("", 204)
        with db() as conn:
            project, snapshot = published_snapshot(conn, project_slug)
            if not snapshot:
                return jsonify(error_body("not_found")), 404
            user = current_user()
            user_id = int(user["id"]) if user else None
            if not user_id:
                client_ip = (request.remote_addr or "unknown").strip() or "unknown"
                if not anonymous_write_allowed(
                    get_rate_limiter(),
                    ip=client_ip,
                    project_id=int(project["id"]),
                ):
                    return jsonify(error_body("rate_limited")), http_status_for("rate_limited")
            status, payload = invoke_snapshot_action(
                conn,
                snapshot=snapshot,
                project=dict(project),
                document_key=document_key,
                body=body,
                user_id=user_id,
                public=True,
            )
            return jsonify(payload), status

    @app.post("/build/<project_slug>/<document_key>/booking")
    @app.post("/builder-runtime/<project_slug>/<document_key>/booking")
    def universal_builder_public_booking(project_slug: str, document_key: str):
        from qr_experience_runtime import public_create_booking
        with db() as conn:
            project, snapshot = published_snapshot(conn, project_slug)
            if not snapshot or not render_document(snapshot, document_key):
                abort(404)
            store = conn.execute("SELECT id FROM stores WHERE workspace_id=? ORDER BY id LIMIT 1", (project["workspace_id"],)).fetchone()
            if not store:
                abort(409, description="This project needs a store before it can accept bookings")
            booking_id = public_create_booking(conn, int(project["workspace_id"]), int(store["id"]), request.form.to_dict())
            document = next((item for item in snapshot.get("documents", []) if (item.get("key") or item.get("document_key")) == document_key), {})
            target = document.get("route") or f"/build/{project_slug}/{document_key}"
            return redirect(f"{target}?booking={booking_id}")

    # Phase 5 uses the same authorization and project-ownership boundary as the
    # Builder Core; only the Marketplace routes live in a separate module.
    from universal_builder_marketplace import register_marketplace_routes
    register_marketplace_routes(app, context, owned_project)
    from desktop.transfer_routes import register_transfer_routes
    register_transfer_routes(app, context, owned_project)
