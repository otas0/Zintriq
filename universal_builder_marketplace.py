"""Phase 5 creation network for Universal Builder.

The Marketplace is deliberately built on the existing package protocol.  A
package is stable identity and every published version is an immutable source
snapshot.  Installation materializes declarative resources into a Project so
published sites never depend on a live Marketplace request.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from uuid import uuid4

_log = logging.getLogger("app.universal_builder")


MARKETPLACE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS builder_creator_profiles (
    id TEXT PRIMARY KEY,
    user_id INTEGER UNIQUE,
    publisher_type TEXT NOT NULL DEFAULT 'individual',
    display_name TEXT NOT NULL,
    handle TEXT NOT NULL UNIQUE,
    avatar TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    trust_level TEXT NOT NULL DEFAULT 'community',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS builder_package_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id TEXT NOT NULL,
    version TEXT NOT NULL,
    manifest TEXT NOT NULL,
    resources TEXT NOT NULL DEFAULT '{}',
    release_notes TEXT DEFAULT '',
    checksum TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'stable',
    status TEXT NOT NULL DEFAULT 'published',
    published_by INTEGER,
    published_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(package_id, version),
    FOREIGN KEY(package_id) REFERENCES builder_packages(id)
);
CREATE INDEX IF NOT EXISTS idx_builder_package_versions_package ON builder_package_versions(package_id,published_at DESC);

CREATE TABLE IF NOT EXISTS builder_package_lineage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id TEXT,
    project_id INTEGER,
    derived_from_package_id TEXT NOT NULL,
    derived_from_version TEXT NOT NULL,
    derivation_type TEXT NOT NULL,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS builder_marketplace_saves (
    user_id INTEGER NOT NULL,
    package_id TEXT NOT NULL,
    collection_name TEXT DEFAULT 'Saved',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, package_id)
);

CREATE TABLE IF NOT EXISTS builder_creator_follows (
    user_id INTEGER NOT NULL,
    creator_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, creator_id)
);

CREATE TABLE IF NOT EXISTS builder_marketplace_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL,
    package_id TEXT,
    creator_id TEXT,
    reason TEXT NOT NULL,
    details TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'reviewing',
    evidence TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS builder_marketplace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    project_id INTEGER,
    package_id TEXT,
    event_type TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_builder_marketplace_events_package ON builder_marketplace_events(package_id,event_type);
"""

PACKAGE_TYPES = {
    "template", "starter_kit", "project", "page", "section", "component",
    "component_library", "theme", "workflow", "data_model", "integration",
    "plugin", "editor_extension", "runtime_adapter", "app_module", "capability",
}
VISIBILITIES = {"private", "unlisted", "public", "official"}
RIGHTS = {"install", "commercial_use", "remix", "fork", "redistribute"}
SECRET_PATTERN = re.compile(
    r"(?:api[_-]?key|secret|access[_-]?token|session[_-]?id|password|private[_-]?key)\s*[:=]",
    re.I,
)
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$")


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def json_load(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        _log.debug("builder_marketplace_json_parse_failed", exc_info=True, extra={"op": "json_load"})
        return fallback


def slugify(value, fallback="creation"):
    value = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return value or fallback


def semver_key(value):
    match = SEMVER_PATTERN.match(str(value or ""))
    if not match:
        return (-1, -1, -1, "")
    return (int(match[1]), int(match[2]), int(match[3]), match[4] or "~")


def _add_columns(conn, table, columns):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_marketplace_tables(conn):
    conn.executescript(MARKETPLACE_SCHEMA_SQL)
    _add_columns(conn, "builder_packages", {
        "creator_id": "TEXT", "slug": "TEXT DEFAULT ''", "name": "TEXT DEFAULT ''",
        "description": "TEXT DEFAULT ''", "visibility": "TEXT NOT NULL DEFAULT 'public'",
        "category": "TEXT DEFAULT ''", "tags": "TEXT NOT NULL DEFAULT '[]'",
        "license_type": "TEXT NOT NULL DEFAULT 'platform_standard'",
        "usage_rights": "TEXT NOT NULL DEFAULT '[\"install\"]'",
        "moderation_status": "TEXT NOT NULL DEFAULT 'active'",
        "latest_version": "TEXT DEFAULT ''", "published_at": "TEXT",
        "deprecated_at": "TEXT", "replacement_package_id": "TEXT",
    })
    _add_columns(conn, "builder_package_installations", {
        "version_text": "TEXT DEFAULT ''", "source": "TEXT NOT NULL DEFAULT 'marketplace'",
        "installation_key": "TEXT DEFAULT ''", "dependency_lock": "TEXT NOT NULL DEFAULT '[]'",
        "resource_map": "TEXT NOT NULL DEFAULT '{}'", "local_state": "TEXT NOT NULL DEFAULT 'linked'",
        "local_modifications": "TEXT NOT NULL DEFAULT '[]'", "updated_at": "TEXT",
    })
    conn.execute(
        """INSERT OR IGNORE INTO builder_creator_profiles
           (id,user_id,publisher_type,display_name,handle,bio,trust_level,status)
           VALUES ('publisher_official_zintriq',NULL,'official','Zintriq','zintriq',
                   'Official Universal Builder resources.','official','active')"""
    )
    _seed_existing_packages(conn)


def _seed_existing_packages(conn):
    rows = conn.execute("SELECT * FROM builder_packages").fetchall()
    for row in rows:
        manifest = json_load(row["manifest"], {})
        version = str(manifest.get("version") or row["version"] or "1.0.0")
        if not SEMVER_PATTERN.match(version):
            version = f"{int(row['version'] or 1)}.0.0"
        creator_id = "publisher_official_zintriq" if row["trust_level"] == "official" else row["creator_id"]
        visibility = "official" if row["trust_level"] == "official" else (row["visibility"] or "public")
        rights = manifest.get("usage_rights") or ["install", "commercial_use", "remix", "fork"]
        conn.execute(
            """UPDATE builder_packages SET creator_id=COALESCE(creator_id,?),slug=CASE WHEN slug='' THEN ? ELSE slug END,
               name=CASE WHEN name='' THEN ? ELSE name END,description=CASE WHEN description='' THEN ? ELSE description END,
               visibility=?,category=CASE WHEN category='' THEN ? ELSE category END,usage_rights=?,latest_version=?,
               published_at=COALESCE(published_at,created_at),moderation_status=COALESCE(moderation_status,'active') WHERE id=?""",
            (creator_id, slugify(manifest.get("name") or row["id"]), manifest.get("name") or row["id"],
             manifest.get("description") or "", visibility, manifest.get("community_category") or manifest.get("package_type") or "",
             json.dumps(rights), version, row["id"]),
        )
        resources = {"template_manifest": manifest} if manifest.get("package_type") == "template" else {}
        checksum = hashlib.sha256(json.dumps({"manifest": manifest, "resources": resources}, sort_keys=True).encode()).hexdigest()
        conn.execute(
            """INSERT OR IGNORE INTO builder_package_versions
               (package_id,version,manifest,resources,release_notes,checksum,status)
               VALUES (?,?,?,?,?,?, 'published')""",
            (row["id"], version, json.dumps(manifest), json.dumps(resources), "Official package migration", checksum),
        )
        versions = conn.execute("SELECT version,manifest FROM builder_package_versions WHERE package_id=? AND status='published'", (row["id"],)).fetchall()
        latest = max(versions, key=lambda item: semver_key(item["version"]), default=None)
        if latest:
            conn.execute("UPDATE builder_packages SET latest_version=?,manifest=? WHERE id=?", (latest["version"], latest["manifest"], row["id"]))


def creator_to_api(conn, row, viewer_id=None):
    if not row:
        return None
    creator_id = row["id"]
    return {
        "id": creator_id, "display_name": row["display_name"], "handle": row["handle"],
        "avatar": row["avatar"] or "", "bio": row["bio"] or "", "publisher_type": row["publisher_type"],
        "trust_level": row["trust_level"], "official": row["trust_level"] == "official",
        "follower_count": conn.execute("SELECT COUNT(*) c FROM builder_creator_follows WHERE creator_id=?", (creator_id,)).fetchone()["c"],
        "following": bool(viewer_id and conn.execute("SELECT 1 FROM builder_creator_follows WHERE user_id=? AND creator_id=?", (viewer_id, creator_id)).fetchone()),
    }


def ensure_creator(conn, user_id, display_name, handle=""):
    existing = conn.execute("SELECT * FROM builder_creator_profiles WHERE user_id=?", (user_id,)).fetchone()
    if existing:
        return existing
    base = slugify(handle or display_name or f"creator-{user_id}", f"creator-{user_id}")
    candidate, suffix = base, 2
    while conn.execute("SELECT 1 FROM builder_creator_profiles WHERE handle=?", (candidate,)).fetchone():
        candidate, suffix = f"{base}-{suffix}", suffix + 1
    creator_id = f"creator_{uuid4().hex}"
    conn.execute(
        "INSERT INTO builder_creator_profiles(id,user_id,display_name,handle) VALUES (?,?,?,?)",
        (creator_id, user_id, display_name or "Creator", candidate),
    )
    return conn.execute("SELECT * FROM builder_creator_profiles WHERE id=?", (creator_id,)).fetchone()


def _version_row(conn, package_id, version=None):
    rows = conn.execute(
        "SELECT * FROM builder_package_versions WHERE package_id=? AND status='published'", (package_id,)
    ).fetchall()
    if version:
        return next((row for row in rows if row["version"] == version), None)
    return max(rows, key=lambda row: semver_key(row["version"]), default=None)


def package_to_api(conn, row, viewer_id=None, detail=False):
    manifest = json_load(row["manifest"], {})
    creator = conn.execute("SELECT * FROM builder_creator_profiles WHERE id=?", (row["creator_id"],)).fetchone()
    latest = _version_row(conn, row["id"])
    result = {
        "id": row["id"], "slug": row["slug"], "name": row["name"] or manifest.get("name") or row["id"],
        "description": row["description"] or manifest.get("description") or "", "package_type": row["package_type"],
        "version": latest["version"] if latest else (row["latest_version"] or str(row["version"])),
        "visibility": row["visibility"], "category": row["category"] or "", "tags": json_load(row["tags"], []),
        "trust_level": row["trust_level"], "status": row["status"], "moderation_status": row["moderation_status"],
        "license_type": row["license_type"], "usage_rights": json_load(row["usage_rights"], ["install"]),
        "creator": creator_to_api(conn, creator, viewer_id), "publisher": row["publisher"],
        "saved": bool(viewer_id and conn.execute("SELECT 1 FROM builder_marketplace_saves WHERE user_id=? AND package_id=?", (viewer_id, row["id"])).fetchone()),
        "install_count": conn.execute("SELECT COUNT(*) c FROM builder_package_installations WHERE package_id=? AND status='active'", (row["id"],)).fetchone()["c"],
        "remix_count": conn.execute("SELECT COUNT(*) c FROM builder_package_lineage WHERE derived_from_package_id=?", (row["id"],)).fetchone()["c"],
        "published_at": row["published_at"], "deprecated": bool(row["deprecated_at"]),
    }
    if detail and latest:
        current_manifest = json_load(latest["manifest"], {})
        result.update({
            "manifest": current_manifest, "required_capabilities": current_manifest.get("required_capabilities") or [],
            "permissions": current_manifest.get("permissions") or [], "dependencies": current_manifest.get("dependencies") or [],
            "compatibility": current_manifest.get("compatibility") or {}, "release_notes": latest["release_notes"] or "",
            "versions": [dict(item) for item in conn.execute(
                "SELECT version,release_notes,channel,published_at FROM builder_package_versions WHERE package_id=? AND status='published' ORDER BY id DESC", (row["id"],)
            ).fetchall()],
            "lineage": [dict(item) for item in conn.execute(
                "SELECT derived_from_package_id,derived_from_version,derivation_type,created_at FROM builder_package_lineage WHERE package_id=? ORDER BY id DESC", (row["id"],)
            ).fetchall()],
        })
    return result


def _detect_secrets(value):
    serialized = json.dumps(value, ensure_ascii=False)
    issues = []
    if SECRET_PATTERN.search(serialized):
        issues.append("Possible secret or credential detected")
    if re.search(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{12,}\b", serialized):
        issues.append("Credential-like token detected")
    return issues


def _component_resources(conn, project_id, definition_id):
    row = conn.execute(
        "SELECT * FROM builder_component_definitions WHERE id=? AND project_id=?", (definition_id, project_id)
    ).fetchone()
    if not row:
        raise ValueError("Component not found")
    definition = dict(row)
    definition.pop("id", None); definition.pop("project_id", None)
    token_keys = json_load(definition.get("token_dependencies"), [])
    tokens = []
    for key in token_keys:
        token = conn.execute("SELECT * FROM builder_design_tokens WHERE project_id=? AND token_key=?", (project_id, key)).fetchone()
        if token:
            item = dict(token); item.pop("id", None); item.pop("project_id", None); tokens.append(item)
    return {"component_definition": definition, "design_tokens": tokens}


def sync_official_component_packages(conn, project_id):
    """Publish selected first-party Creator resources through the shared protocol."""
    specifications = {
        "official.product-card": ("zintriq/product-card", "Commerce", ["commerce"], []),
        "official.customer-navigation": ("zintriq/customer-navigation", "Navigation", ["navigation"], []),
        "official.business-app-shell": ("zintriq/business-app-shell", "Business", ["core", "navigation"], ["builder.read"]),
    }
    for component_key, (package_id, category, capabilities, permissions) in specifications.items():
        definition = conn.execute(
            "SELECT * FROM builder_component_definitions WHERE project_id=? AND component_key=?", (project_id, component_key)
        ).fetchone()
        if not definition:
            continue
        resources = _component_resources(conn, project_id, definition["id"])
        version = f"{int(definition['version'] or 1)}.0.0"
        manifest = {
            "id": package_id, "name": definition["name"], "description": definition["description"] or "Official reusable Builder component.",
            "publisher": "Zintriq", "version": version, "schema_version": 5, "package_type": "component",
            "dependencies": [], "required_capabilities": capabilities, "permissions": permissions,
            "compatibility": {"builder_schema": ">=4 <6", "component_registry": ">=1"},
            "entry_resources": ["component_definition"], "usage_rights": ["install", "commercial_use", "remix", "fork"],
        }
        conn.execute(
            """INSERT INTO builder_packages
               (id,package_type,publisher,version,manifest,trust_level,status,creator_id,slug,name,description,visibility,
                category,tags,license_type,usage_rights,moderation_status,latest_version,published_at,updated_at)
               VALUES (?,?,'Zintriq',1,?,'official','active','publisher_official_zintriq',?,?,?,?,?,'[]','platform_standard',
                       '[\"install\",\"commercial_use\",\"remix\",\"fork\"]','active',?,?,?)
               ON CONFLICT(id) DO UPDATE SET manifest=excluded.manifest,name=excluded.name,description=excluded.description,
                 category=excluded.category,latest_version=excluded.latest_version,updated_at=excluded.updated_at""",
            (package_id, "component", json.dumps(manifest), slugify(definition["name"]), definition["name"],
             definition["description"] or "Official reusable Builder component.", "official", category, version, now(), now()),
        )
        checksum = hashlib.sha256(json.dumps({"manifest": manifest, "resources": resources}, sort_keys=True).encode()).hexdigest()
        conn.execute(
            """INSERT OR IGNORE INTO builder_package_versions
               (package_id,version,manifest,resources,release_notes,checksum,channel,status)
               VALUES (?,?,?,?,?,?,'stable','published')""",
            (package_id, version, json.dumps(manifest), json.dumps(resources), "Official Creator System release", checksum),
        )


def sync_official_template_snapshot(conn, project_id):
    """Create a sanitized, immutable source for template Remix operations."""
    package = conn.execute("SELECT * FROM builder_packages WHERE id='zintriq-system'").fetchone()
    if not package or _version_row(conn, "zintriq-system", "3.1.0"):
        return
    from universal_builder_core import capture_project_snapshot
    snapshot = capture_project_snapshot(conn, project_id)
    snapshot["data_records"] = []
    snapshot["entry_points"] = []
    snapshot["route_ownership"] = []
    source_project = snapshot.get("project") or {}
    source_project.update({"name": "Business & Customer App", "legacy_source_type": None, "legacy_source_id": None, "status": "draft"})
    source_project["settings"] = {
        "runtime_adapter": "hybrid_strangler", "preserve_existing_routes": True,
        "customer_and_business_are_one_template": True,
    }
    manifest = json_load(package["manifest"], {})
    manifest["version"] = "3.1.0"
    manifest["lineage"] = {"official_source_project": True, "sanitized": True}
    resources = {"template_manifest": manifest, "project_snapshot": snapshot, "sample_data": False}
    checksum = hashlib.sha256(json.dumps({"manifest": manifest, "resources": resources}, sort_keys=True).encode()).hexdigest()
    conn.execute(
        """INSERT INTO builder_package_versions(package_id,version,manifest,resources,release_notes,checksum,channel,status)
           VALUES ('zintriq-system','3.1.0',?,?,?,?,'stable','published')""",
        (json.dumps(manifest), json.dumps(resources), "Sanitized immutable Project snapshot for safe Remix", checksum),
    )
    conn.execute("UPDATE builder_packages SET manifest=?,latest_version='3.1.0',updated_at=? WHERE id='zintriq-system'", (json.dumps(manifest), now()))


def publish_component(conn, *, project_id, definition_id, user_id, metadata):
    project = conn.execute("SELECT * FROM builder_projects WHERE id=?", (project_id,)).fetchone()
    if not project:
        raise ValueError("Project not found")
    resources = _component_resources(conn, project_id, definition_id)
    definition = resources["component_definition"]
    errors = _detect_secrets(resources)
    if errors:
        raise ValueError(errors[0])
    creator = ensure_creator(conn, user_id, metadata.get("creator_name") or "Creator", metadata.get("creator_handle") or "")
    version = str(metadata.get("version") or "1.0.0")
    if not SEMVER_PATTERN.match(version):
        raise ValueError("Version must use semantic versioning, for example 1.0.0")
    rights = list(dict.fromkeys(metadata.get("usage_rights") or ["install", "commercial_use", "remix", "fork"]))
    if any(right not in RIGHTS for right in rights):
        raise ValueError("Unsupported usage right")
    package_id = str(metadata.get("package_id") or "").strip()
    package = conn.execute("SELECT * FROM builder_packages WHERE id=?", (package_id,)).fetchone() if package_id else None
    if package and package["creator_id"] != creator["id"]:
        raise PermissionError("This package belongs to another creator")
    if not package:
        package_id = f"pkg_{uuid4().hex}"
        base_slug = slugify(metadata.get("name") or definition["name"])
        slug, suffix = base_slug, 2
        while conn.execute("SELECT 1 FROM builder_packages WHERE creator_id=? AND slug=?", (creator["id"], slug)).fetchone():
            slug, suffix = f"{base_slug}-{suffix}", suffix + 1
        name = str(metadata.get("name") or definition["name"])
        description = str(metadata.get("description") or definition.get("description") or "")
        manifest = {}
        conn.execute(
            """INSERT INTO builder_packages
               (id,package_type,publisher,version,manifest,trust_level,status,creator_id,slug,name,description,
                visibility,category,tags,license_type,usage_rights,moderation_status,latest_version,published_at,updated_at)
               VALUES (?,?,?,1,?,'community','active',?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
            (package_id, "component", creator["display_name"], json.dumps(manifest), creator["id"], slug, name, description,
             metadata.get("visibility") if metadata.get("visibility") in VISIBILITIES else "public",
             metadata.get("category") or "Components", json.dumps(metadata.get("tags") or []),
             metadata.get("license_type") or "platform_standard", json.dumps(rights), version, now(), now()),
        )
    package = conn.execute("SELECT * FROM builder_packages WHERE id=?", (package_id,)).fetchone()
    if _version_row(conn, package_id, version):
        raise ValueError(f"Version {version} already exists and cannot be changed")
    manifest = {
        "id": package_id, "name": package["name"], "description": package["description"],
        "publisher": creator["display_name"], "version": version, "schema_version": 5,
        "package_type": "component", "dependencies": metadata.get("dependencies") or [],
        "required_capabilities": metadata.get("required_capabilities") or [],
        "permissions": metadata.get("permissions") or [],
        "compatibility": {"builder_schema": ">=4 <6", "component_registry": ">=1"},
        "entry_resources": ["component_definition"], "design_token_dependencies": [item["token_key"] for item in resources["design_tokens"]],
        "lineage": metadata.get("lineage") or {}, "usage_rights": json_load(package["usage_rights"], rights),
    }
    from universal_builder_packages import validate_package_manifest
    validation = validate_package_manifest(manifest)
    validation.extend(_detect_secrets({"manifest": manifest, "resources": resources}))
    if validation:
        raise ValueError(validation[0])
    checksum = hashlib.sha256(json.dumps({"manifest": manifest, "resources": resources}, sort_keys=True).encode()).hexdigest()
    conn.execute(
        """INSERT INTO builder_package_versions
           (package_id,version,manifest,resources,release_notes,checksum,channel,status,published_by)
           VALUES (?,?,?,?,?,?,?,'published',?)""",
        (package_id, version, json.dumps(manifest), json.dumps(resources), metadata.get("release_notes") or "Initial release",
         checksum, metadata.get("channel") or "stable", user_id),
    )
    conn.execute(
        "UPDATE builder_packages SET manifest=?,latest_version=?,version=version+1,updated_at=? WHERE id=?",
        (json.dumps(manifest), version, now(), package_id),
    )
    return package_to_api(conn, conn.execute("SELECT * FROM builder_packages WHERE id=?", (package_id,)).fetchone(), user_id, True)


def _resolve_dependencies(conn, manifest, visiting=None, resolved=None):
    visiting, resolved = visiting or set(), resolved or []
    for dependency in manifest.get("dependencies") or []:
        if isinstance(dependency, str):
            package_id, required = dependency.split("@", 1) if "@" in dependency else (dependency, "")
            optional = False
        else:
            package_id, required, optional = dependency.get("package_id"), dependency.get("version", ""), bool(dependency.get("optional"))
        if not package_id or package_id in {item["package_id"] for item in resolved}:
            continue
        if package_id in visiting:
            raise ValueError("Circular package dependency detected")
        package = conn.execute("SELECT * FROM builder_packages WHERE id=? AND status='active' AND moderation_status='active'", (package_id,)).fetchone()
        version = _version_row(conn, package_id) if package else None
        if not package or not version:
            if optional:
                continue
            raise ValueError(f"Required dependency {package_id} is unavailable")
        if required and required[0].isdigit() and version["version"] != required:
            raise ValueError(f"Dependency {package_id} requires version {required}")
        visiting.add(package_id)
        _resolve_dependencies(conn, json_load(version["manifest"], {}), visiting, resolved)
        visiting.remove(package_id)
        resolved.append({"package_id": package_id, "version": version["version"]})
    return resolved


def install_preview(conn, project, package_id, version=None):
    package = conn.execute(
        "SELECT * FROM builder_packages WHERE id=? AND status='active' AND moderation_status='active'", (package_id,)
    ).fetchone()
    selected = _version_row(conn, package_id, version) if package else None
    if not package or not selected:
        raise ValueError("Package version is not available")
    manifest, resources = json_load(selected["manifest"], {}), json_load(selected["resources"], {})
    dependencies = _resolve_dependencies(conn, manifest)
    all_permissions = list(manifest.get("permissions") or [])
    all_requirements = list(manifest.get("required_capabilities") or [])
    for dependency in dependencies:
        dependency_version = _version_row(conn, dependency["package_id"], dependency["version"])
        dependency_manifest = json_load(dependency_version["manifest"], {})
        all_permissions.extend(dependency_manifest.get("permissions") or [])
        all_requirements.extend(dependency_manifest.get("required_capabilities") or [])
    all_permissions = list(dict.fromkeys(all_permissions)); all_requirements = list(dict.fromkeys(all_requirements))
    capabilities = json_load(project["enabled_capabilities"], [])
    missing = [item for item in all_requirements if item not in capabilities]
    return {
        "package": package_to_api(conn, package, detail=True), "version": selected["version"],
        "dependencies": dependencies, "permissions": all_permissions,
        "missing_capabilities": missing, "resources": {
            "components": 1 if resources.get("component_definition") else 0,
            "tokens": len(resources.get("design_tokens") or []),
            "template": bool(resources.get("template_manifest")),
        },
    }


def _materialize_component(conn, project_id, package_id, resources):
    definition = dict(resources["component_definition"])
    original_key = definition.get("component_key") or slugify(definition.get("name"), "component").replace("-", ".")
    key = f"marketplace.{package_id[:12]}.{original_key}"
    existing = conn.execute("SELECT * FROM builder_component_definitions WHERE project_id=? AND component_key=?", (project_id, key)).fetchone()
    values = [
        project_id, key, definition.get("name") or "Marketplace Component", definition.get("description") or "",
        definition.get("version") or 1, definition.get("root_structure") or "[]", definition.get("property_schema") or "{}",
        definition.get("slots") or "{}", definition.get("variants") or "{}", definition.get("default_variant") or "default",
        definition.get("data_inputs") or "{}", definition.get("events") or "[]", definition.get("token_dependencies") or "[]",
        json.dumps({**json_load(definition.get("metadata"), {}), "source_package_id": package_id, "linked": True}), now(),
    ]
    if existing:
        conn.execute(
            """UPDATE builder_component_definitions SET name=?,description=?,version=?,root_structure=?,property_schema=?,slots=?,variants=?,
               default_variant=?,data_inputs=?,events=?,token_dependencies=?,metadata=?,updated_at=? WHERE id=?""",
            [*values[2:14], values[14], existing["id"]],
        )
        definition_id = existing["id"]
    else:
        cur = conn.execute(
            """INSERT INTO builder_component_definitions
               (project_id,component_key,name,description,version,root_structure,property_schema,slots,variants,default_variant,
                data_inputs,events,token_dependencies,metadata,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values,
        )
        definition_id = cur.lastrowid
    token_map = {}
    for token in resources.get("design_tokens") or []:
        source_key = token["token_key"]
        found = conn.execute("SELECT * FROM builder_design_tokens WHERE project_id=? AND token_key=?", (project_id, source_key)).fetchone()
        target_key = source_key
        if found and found["values_json"] != token.get("values_json"):
            target_key = f"package.{package_id[:8]}.{source_key}"
        conn.execute(
            """INSERT INTO builder_design_tokens(project_id,token_key,name,category,group_name,values_json,description,updated_at)
               VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(project_id,token_key) DO NOTHING""",
            (project_id, target_key, token.get("name") or target_key, token.get("category") or "color",
             token.get("group_name") or "Marketplace", token.get("values_json") or "{}", token.get("description") or "", now()),
        )
        token_map[source_key] = target_key
    return {"component_definition_id": definition_id, "component_key": key, "tokens": token_map}


def install_package(conn, *, project, package_id, user_id, granted_permissions, version=None, updating=False):
    preview = install_preview(conn, project, package_id, version)
    required = set(preview["permissions"])
    if required - set(granted_permissions or []):
        raise PermissionError("Required package permissions were not approved")
    selected = _version_row(conn, package_id, preview["version"])
    manifest, resources = json_load(selected["manifest"], {}), json_load(selected["resources"], {})
    enabled = json_load(project["enabled_capabilities"], [])
    # Capabilities must already exist in the project: packages cannot grant them to themselves.
    if preview["missing_capabilities"]:
        raise PermissionError("Project is missing required capabilities: " + ", ".join(preview["missing_capabilities"]))
    resource_map = {}
    if resources.get("component_definition"):
        resource_map = _materialize_component(conn, project["id"], package_id, resources)
    lock = [*preview["dependencies"], {"package_id": package_id, "version": selected["version"]}]
    existing = conn.execute("SELECT * FROM builder_package_installations WHERE project_id=? AND package_id=?", (project["id"], package_id)).fetchone()
    if updating and existing:
        from universal_builder_core import create_project_revision
        create_project_revision(conn, project["id"], user_id, f"Before updating {preview['package']['name']} to {selected['version']}")
    # Dependencies are resolved first and materialized using their immutable
    # versions.  The enclosing request transaction commits the complete graph.
    for dependency in preview["dependencies"]:
        dependency_package_id, dependency_version_text = dependency["package_id"], dependency["version"]
        dependency_version = _version_row(conn, dependency_package_id, dependency_version_text)
        dependency_resources = json_load(dependency_version["resources"], {})
        dependency_map = _materialize_component(conn, project["id"], dependency_package_id, dependency_resources) if dependency_resources.get("component_definition") else {}
        dependency_manifest = json_load(dependency_version["manifest"], {})
        dependency_lock = _resolve_dependencies(conn, dependency_manifest) + [{"package_id": dependency_package_id, "version": dependency_version_text}]
        conn.execute(
            """INSERT INTO builder_package_installations
               (project_id,package_id,version,version_text,granted_permissions,status,source,installation_key,dependency_lock,resource_map,local_state,updated_at)
               VALUES (?,?,1,?,?,'active','dependency',?,?,?,'linked',?)
               ON CONFLICT(project_id,package_id) DO UPDATE SET version_text=excluded.version_text,status='active',
                 dependency_lock=excluded.dependency_lock,resource_map=excluded.resource_map,updated_at=excluded.updated_at""",
            (project["id"], dependency_package_id, dependency_version_text,
             json.dumps(dependency_manifest.get("permissions") or []), uuid4().hex,
             json.dumps(dependency_lock), json.dumps(dependency_map), now()),
        )
    conn.execute(
        """INSERT INTO builder_package_installations
           (project_id,package_id,version,version_text,granted_permissions,status,source,installation_key,dependency_lock,resource_map,local_state,updated_at)
           VALUES (?,?,1,?,?,'active','marketplace',?,?,?,'linked',?)
           ON CONFLICT(project_id,package_id) DO UPDATE SET version_text=excluded.version_text,
             granted_permissions=excluded.granted_permissions,status='active',dependency_lock=excluded.dependency_lock,
             resource_map=excluded.resource_map,updated_at=excluded.updated_at""",
        (project["id"], package_id, selected["version"], json.dumps(sorted(required)), uuid4().hex,
         json.dumps(lock), json.dumps(resource_map), now()),
    )
    conn.execute(
        "INSERT INTO builder_marketplace_events(user_id,project_id,package_id,event_type,metadata) VALUES (?,?,?,?,?)",
        (user_id, project["id"], package_id, "update" if updating else "install", json.dumps({"version": selected["version"]})),
    )
    return {"ok": True, "package": preview["package"], "installed_version": selected["version"], "resource_map": resource_map,
            "message": f"{preview['package']['name']} {'updated' if updating else 'installed'}"}


def installation_to_api(conn, row):
    package = conn.execute("SELECT * FROM builder_packages WHERE id=?", (row["package_id"],)).fetchone()
    current = row["version_text"] or str(row["version"])
    latest = _version_row(conn, row["package_id"])
    return {
        **dict(row), "version": current, "dependency_lock": json_load(row["dependency_lock"], []),
        "resource_map": json_load(row["resource_map"], {}), "local_modifications": json_load(row["local_modifications"], []),
        "package": package_to_api(conn, package) if package else None,
        "latest_version": latest["version"] if latest else current,
        "update_available": bool(latest and semver_key(latest["version"]) > semver_key(current)),
    }


def register_marketplace_routes(app, context, owned_project):
    from flask import abort, jsonify, render_template, request
    from app import current_user, db, login_required

    def user_name(user):
        return user.get("name") or user.get("display_name") or user.get("email", "Creator").split("@")[0]

    @app.get("/app/marketplace")
    @login_required
    def marketplace_home():
        from app import workspace_snapshot
        owner_id = current_user()["id"]
        return render_template(
            "zintriq/marketplace.html",
            page_title="Marketplace",
            workspace=workspace_snapshot(owner_id),
        )

    @app.get("/api/marketplace/packages")
    @login_required
    def marketplace_packages():
        user = current_user()
        query, package_type, category = request.args.get("q", "").strip().lower(), request.args.get("type", ""), request.args.get("category", "")
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM builder_packages WHERE status='active' AND moderation_status='active' AND visibility IN ('public','official') ORDER BY trust_level='official' DESC,published_at DESC,id"
            ).fetchall()
            items = [package_to_api(conn, row, int(user["id"])) for row in rows]
            if query:
                items = [item for item in items if query in " ".join([item["name"], item["description"], item["publisher"], item["category"], *item["tags"]]).lower()]
            if package_type:
                items = [item for item in items if item["package_type"] == package_type]
            if category:
                items = [item for item in items if item["category"].lower() == category.lower()]
            return jsonify({"packages": items, "count": len(items)})

    @app.get("/api/marketplace/packages/<path:package_id>")
    @login_required
    def marketplace_package_detail(package_id):
        user = current_user()
        with db() as conn:
            row = conn.execute("SELECT * FROM builder_packages WHERE id=?", (package_id,)).fetchone()
            viewer_profile = conn.execute("SELECT id FROM builder_creator_profiles WHERE user_id=?", (user["id"],)).fetchone()
            if not row or (row["visibility"] == "private" and row["creator_id"] != (viewer_profile["id"] if viewer_profile else None)):
                abort(404)
            conn.execute("INSERT INTO builder_marketplace_events(user_id,package_id,event_type) VALUES (?,?,'view')", (user["id"], package_id))
            return jsonify(package_to_api(conn, row, int(user["id"]), True))

    @app.get("/api/marketplace/creators/<handle>")
    @login_required
    def marketplace_creator(handle):
        user = current_user()
        with db() as conn:
            creator = conn.execute("SELECT * FROM builder_creator_profiles WHERE handle=? AND status='active'", (handle,)).fetchone()
            if not creator: abort(404)
            packages = conn.execute("SELECT * FROM builder_packages WHERE creator_id=? AND status='active' AND visibility IN ('public','official')", (creator["id"],)).fetchall()
            return jsonify({"creator": creator_to_api(conn, creator, int(user["id"])), "packages": [package_to_api(conn, row, int(user["id"])) for row in packages]})

    @app.post("/api/marketplace/creator-profile")
    @login_required
    def marketplace_creator_create():
        user = current_user(); context("builder.create"); data = request.get_json(silent=True) or {}
        with db() as conn:
            profile = ensure_creator(conn, int(user["id"]), str(data.get("display_name") or user_name(user)), str(data.get("handle") or ""))
            if data.get("bio") is not None:
                conn.execute("UPDATE builder_creator_profiles SET bio=?,updated_at=? WHERE id=?", (str(data["bio"])[:500], now(), profile["id"]))
                profile = conn.execute("SELECT * FROM builder_creator_profiles WHERE id=?", (profile["id"],)).fetchone()
            return jsonify(creator_to_api(conn, profile, int(user["id"]))), 201

    @app.post("/api/marketplace/projects/<int:project_id>/components/<int:definition_id>/publish")
    @login_required
    def marketplace_publish_component(project_id, definition_id):
        user = current_user(); _, workspace_id = context("builder.publish"); data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            try:
                result = publish_component(conn, project_id=project_id, definition_id=definition_id, user_id=int(user["id"]), metadata=data)
            except PermissionError as exc:
                return jsonify({"error": str(exc)}), 403
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            conn.execute("INSERT INTO builder_marketplace_events(user_id,project_id,package_id,event_type) VALUES (?,?,?,'publish')", (user["id"], project_id, result["id"]))
            return jsonify(result), 201

    @app.get("/api/marketplace/projects/<int:project_id>/installed")
    @login_required
    def marketplace_installed(project_id):
        workspace_id = session.get("active_workspace_id")
        if not workspace_id:
            abort(400)
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            rows = conn.execute("SELECT * FROM builder_package_installations WHERE project_id=? AND status='active' ORDER BY installed_at DESC", (project_id,)).fetchall()
            return jsonify({"installations": [installation_to_api(conn, row) for row in rows]})

    @app.post("/api/marketplace/projects/<int:project_id>/packages/<path:package_id>/preview-install")
    @login_required
    def marketplace_install_preview(project_id, package_id):
        workspace_id = session.get("active_workspace_id")
        if not workspace_id:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            try: return jsonify(install_preview(conn, project, package_id, data.get("version")))
            except ValueError as exc: return jsonify({"error": str(exc)}), 400

    @app.post("/api/marketplace/projects/<int:project_id>/packages/<path:package_id>/install")
    @login_required
    def marketplace_install(project_id, package_id):
        user = current_user()
        workspace_id = session.get("active_workspace_id")
        if not workspace_id:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            try:
                return jsonify(install_package(conn, project=project, package_id=package_id, user_id=int(user["id"]),
                                               granted_permissions=data.get("granted_permissions") or [], version=data.get("version"))), 201
            except PermissionError as exc: return jsonify({"error": str(exc)}), 403
            except ValueError as exc: return jsonify({"error": str(exc)}), 409

    @app.post("/api/marketplace/projects/<int:project_id>/packages/<path:package_id>/update")
    @login_required
    def marketplace_update(project_id, package_id):
        user = current_user()
        workspace_id = session.get("active_workspace_id")
        if not workspace_id:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            installation = conn.execute("SELECT * FROM builder_package_installations WHERE project_id=? AND package_id=? AND status='active'", (project_id, package_id)).fetchone()
            if not installation: abort(404)
            if installation["local_state"] == "modified" and not data.get("resolution"):
                return jsonify({"error": "Local changes need a decision", "options": ["keep_local", "accept_package", "fork"]}), 409
            try:
                return jsonify(install_package(conn, project=project, package_id=package_id, user_id=int(user["id"]),
                                               granted_permissions=data.get("granted_permissions") or json_load(installation["granted_permissions"], []),
                                               version=data.get("version"), updating=True))
            except PermissionError as exc: return jsonify({"error": str(exc)}), 403
            except ValueError as exc: return jsonify({"error": str(exc)}), 409

    @app.delete("/api/marketplace/projects/<int:project_id>/packages/<path:package_id>")
    @login_required
    def marketplace_remove(project_id, package_id):
        workspace_id = session.get("active_workspace_id")
        if not workspace_id:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            owned_project(conn, project_id, workspace_id)
            installation = conn.execute("SELECT * FROM builder_package_installations WHERE project_id=? AND package_id=? AND status='active'", (project_id, package_id)).fetchone()
            if not installation: abort(404)
            resource_map = json_load(installation["resource_map"], {})
            definition_id = resource_map.get("component_definition_id")
            usage = conn.execute("SELECT COUNT(*) c FROM builder_component_instances WHERE project_id=? AND component_definition_id=?", (project_id, definition_id)).fetchone()["c"] if definition_id else 0
            dependents = conn.execute("SELECT * FROM builder_package_installations WHERE project_id=? AND status='active' AND package_id<>?", (project_id, package_id)).fetchall()
            dependent_ids = [row["package_id"] for row in dependents if package_id in {item.get("package_id") for item in json_load(row["dependency_lock"], [])}]
            if (usage or dependent_ids) and data.get("resolution") != "detach_local_resources":
                return jsonify({"error": "Package is still in use", "component_instances": usage, "dependent_packages": dependent_ids,
                                "options": ["cancel", "detach_local_resources"]}), 409
            if data.get("resolution") == "detach_local_resources":
                # Keep the materialized resources as plain local copies; stop tracking the package.
                if definition_id:
                    definition = conn.execute("SELECT metadata FROM builder_component_definitions WHERE id=? AND project_id=?", (definition_id, project_id)).fetchone()
                    if definition:
                        metadata = {**json_load(definition["metadata"], {}), "linked": False, "detached": True}
                        conn.execute("UPDATE builder_component_definitions SET metadata=?,updated_at=? WHERE id=?", (json.dumps(metadata), now(), definition_id))
                conn.execute("UPDATE builder_package_installations SET status='detached',local_state='detached',updated_at=? WHERE id=?", (now(), installation["id"]))
                return jsonify({"ok": True, "detached": True, "component_instances": usage, "dependent_packages": dependent_ids})
            if definition_id:
                conn.execute("DELETE FROM builder_component_definitions WHERE id=? AND project_id=?", (definition_id, project_id))
            conn.execute("UPDATE builder_package_installations SET status='removed',updated_at=? WHERE id=?", (now(), installation["id"]))
            return jsonify({"ok": True, "removed": True})

    @app.post("/api/marketplace/packages/<path:package_id>/remix")
    @login_required
    def marketplace_remix(package_id):
        user = current_user(); _, workspace_id = context("builder.create"); data = request.get_json(silent=True) or {}
        with db() as conn:
            package = conn.execute("SELECT * FROM builder_packages WHERE id=? AND status='active' AND moderation_status='active'", (package_id,)).fetchone()
            if not package: abort(404)
            if "remix" not in json_load(package["usage_rights"], []): return jsonify({"error": "This creation does not allow remixing"}), 403
            version = _version_row(conn, package_id, data.get("version"))
            if package["package_type"] != "template": return jsonify({"error": "Use Fork for reusable resources"}), 400
            manifest, resources = json_load(version["manifest"], {}), json_load(version["resources"], {})
            remix_name = str(data.get("name") or f"My {package['name']}")[:80]
            try:
                if resources.get("project_snapshot"):
                    from universal_builder_core import create_blank_project, restore_project_snapshot
                    project_id = create_blank_project(conn, workspace_id, remix_name, int(user["id"]))
                    restore_project_snapshot(conn, project_id, resources["project_snapshot"])
                    conn.execute("UPDATE builder_projects SET name=?,template_id=?,template_version=1,legacy_source_type=NULL,legacy_source_id=NULL,status='draft',updated_at=? WHERE id=?", (remix_name, manifest.get("id") or package_id, now(), project_id))
                else:
                    from universal_builder_core import create_project_from_template
                    template_id = manifest.get("id") if conn.execute("SELECT 1 FROM builder_templates WHERE id=?", (manifest.get("id"),)).fetchone() else package_id
                    project_id = create_project_from_template(conn, workspace_id, template_id, remix_name, int(user["id"]))
            except ValueError as exc: return jsonify({"error": str(exc)}), 400
            conn.execute("INSERT INTO builder_package_lineage(project_id,derived_from_package_id,derived_from_version,derivation_type,created_by) VALUES (?,?,?,'remix',?)", (project_id, package_id, version["version"], user["id"]))
            conn.execute("INSERT INTO builder_marketplace_events(user_id,project_id,package_id,event_type) VALUES (?,?,?,'remix')", (user["id"], project_id, package_id))
            return jsonify({"ok": True, "project_id": project_id, "lineage": {"package_id": package_id, "version": version["version"], "type": "remix"}}), 201

    @app.post("/api/marketplace/projects/<int:project_id>/packages/<path:package_id>/fork")
    @login_required
    def marketplace_fork(project_id, package_id):
        user = current_user(); _, workspace_id = context("builder.update"); data = request.get_json(silent=True) or {}
        with db() as conn:
            project = owned_project(conn, project_id, workspace_id)
            package = conn.execute("SELECT * FROM builder_packages WHERE id=? AND status='active'", (package_id,)).fetchone()
            if not package: abort(404)
            if "fork" not in json_load(package["usage_rights"], []): return jsonify({"error": "This creation does not allow forking"}), 403
            version = _version_row(conn, package_id, data.get("version")); resources = json_load(version["resources"], {})
            if not resources.get("component_definition"): return jsonify({"error": "This package has no forkable Component"}), 400
            resource_map = _materialize_component(conn, project_id, f"fork_{uuid4().hex[:12]}", resources)
            definition_id = resource_map["component_definition_id"]
            conn.execute("UPDATE builder_component_definitions SET name=?,metadata=?,updated_at=? WHERE id=?", (
                str(data.get("name") or f"{package['name']} Remix"), json.dumps({"source": "fork", "lineage": {"package_id": package_id, "version": version["version"]}}), now(), definition_id))
            result = publish_component(conn, project_id=project_id, definition_id=definition_id, user_id=int(user["id"]), metadata={
                **data, "name": data.get("name") or f"{package['name']} Remix", "version": data.get("new_version") or "1.0.0",
                "lineage": {"derived_from_package_id": package_id, "derived_from_version": version["version"], "derivation_type": "fork"},
            })
            conn.execute("INSERT INTO builder_package_lineage(package_id,project_id,derived_from_package_id,derived_from_version,derivation_type,created_by) VALUES (?,?,?,?,'fork',?)", (result["id"], project_id, package_id, version["version"], user["id"]))
            conn.execute("INSERT INTO builder_marketplace_events(user_id,project_id,package_id,event_type) VALUES (?,?,?,'fork')", (user["id"], project_id, package_id))
            result = package_to_api(conn, conn.execute("SELECT * FROM builder_packages WHERE id=?", (result["id"],)).fetchone(), int(user["id"]), True)
            return jsonify({"package": result, "component_definition_id": definition_id}), 201

    @app.post("/api/marketplace/packages/<path:package_id>/save")
    @login_required
    def marketplace_save(package_id):
        user = current_user()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            if not conn.execute("SELECT 1 FROM builder_packages WHERE id=?", (package_id,)).fetchone(): abort(404)
            exists = conn.execute("SELECT 1 FROM builder_marketplace_saves WHERE user_id=? AND package_id=?", (user["id"], package_id)).fetchone()
            if exists: conn.execute("DELETE FROM builder_marketplace_saves WHERE user_id=? AND package_id=?", (user["id"], package_id))
            else: conn.execute("INSERT INTO builder_marketplace_saves(user_id,package_id,collection_name) VALUES (?,?,?)", (user["id"], package_id, str(data.get("collection") or "Saved")))
            return jsonify({"saved": not bool(exists)})

    @app.post("/api/marketplace/creators/<creator_id>/follow")
    @login_required
    def marketplace_follow(creator_id):
        user = current_user()
        with db() as conn:
            if not conn.execute("SELECT 1 FROM builder_creator_profiles WHERE id=?", (creator_id,)).fetchone(): abort(404)
            exists = conn.execute("SELECT 1 FROM builder_creator_follows WHERE user_id=? AND creator_id=?", (user["id"], creator_id)).fetchone()
            if exists: conn.execute("DELETE FROM builder_creator_follows WHERE user_id=? AND creator_id=?", (user["id"], creator_id))
            else: conn.execute("INSERT INTO builder_creator_follows(user_id,creator_id) VALUES (?,?)", (user["id"], creator_id))
            return jsonify({"following": not bool(exists)})

    @app.post("/api/marketplace/packages/<path:package_id>/report")
    @login_required
    def marketplace_report(package_id):
        user = current_user()
        data = request.get_json(silent=True) or {}
        reason = str(data.get("reason") or "").strip()
        if reason not in {"spam", "malicious", "copyright", "misleading", "unsafe", "privacy", "broken"}:
            return jsonify({"error": "Choose a valid report reason"}), 400
        with db() as conn:
            if not conn.execute("SELECT 1 FROM builder_packages WHERE id=?", (package_id,)).fetchone(): abort(404)
            cur = conn.execute("INSERT INTO builder_marketplace_reports(reporter_id,package_id,reason,details) VALUES (?,?,?,?)", (user["id"], package_id, reason, str(data.get("details") or "")[:1000]))
            return jsonify({"ok": True, "report_id": cur.lastrowid, "status": "reviewing"}), 201
