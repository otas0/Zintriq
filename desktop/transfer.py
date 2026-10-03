"""Desktop project packages.

A ``.zintriq`` file is a zip. Checksums prove the bytes were not changed.
They do not prove who created the package. Imported files are untrusted:
members are read individually, automations stay off, and the write is one
transaction. SVG is rejected rather than sanitized.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import stat
import struct
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from db_adapter import commit_with_retry
from universal_builder_core import _slug


SCHEMA_VERSION = 1
REDACTED = "需要重新配置"
PREVIEW_WARNING = "包内可能含个人信息"
_ALWAYS_IGNORED = "预订、客户、反馈、订单和连接密钥不会写入作品包"

_CONTENT_FILES = (
    "manifest.json",
    "content/project.json",
    "content/pages.json",
    "content/components.json",
    "content/collections.json",
    "content/workflows.json",
    "content/design.json",
    "content/redactions.json",
    "content/omitted.json",
    "content/external_urls.json",
)
_REQUIRED = {"manifest.json", "checksums.json", "content/project.json"}
_ASSET_NAME = re.compile(r"^assets/[a-f0-9]{16}\.(png|jpg|gif|webp|woff|woff2|ttf|otf)$")
_KEY = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_TOKEN_KEY = re.compile(r"^[A-Za-z0-9_-]{1,40}(?:\.[A-Za-z0-9_-]{1,40}){0,4}$")
_ENABLE_KEY = re.compile(r"^(action|interaction|workflow|entry):[A-Za-z0-9_-]{1,80}$")
_ROUTE = re.compile(r"^/[A-Za-z0-9_\-./]{0,200}$")
_UPLOAD_URL = re.compile(r"(?:/static/uploads/|/uploads/)([A-Za-z0-9][A-Za-z0-9._-]{0,80})")
_ASSET_POINTER = re.compile(r"asset:(assets/[a-f0-9]{16}\.(?:png|jpg|gif|webp|woff|woff2|ttf|otf))")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_SK = re.compile(r"sk_[A-Za-z0-9]{8,}")
_BEARER = re.compile(r"bearer\s+\S+", re.I)
_TOKEN_QUERY = re.compile(r"[?&](?:token|key|secret|password|access_token)=", re.I)
_WEBHOOK = re.compile(
    r"https?://[^\s\"']*(?:webhook|hooks\.slack\.com|discord(?:app)?\.com/api/webhooks)",
    re.I,
)
_RANDOM = re.compile(r"^[A-Za-z0-9_\-+/=]{32,}$")
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}
_ARCHIVE_SUFFIXES = (".zip", ".zintriq", ".gz", ".tgz", ".7z", ".rar", ".tar")
_SECRET_FOLDED = {
    "apikey", "secret", "password", "passwd", "accesstoken", "refreshtoken",
    "privatekey", "clientsecret", "credential", "credentials", "authorization",
    "authtoken", "webhooksecret", "sessiontoken", "secretkey", "token",
}
_OMITTED_LABELS = {
    "data_records": "数据记录",
    "deployments": "部署",
    "runtime_events": "运行事件",
    "revisions": "修订",
    "installations": "已安装的包",
}
_ASSET_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "woff": "font/woff",
    "woff2": "font/woff2",
    "ttf": "font/ttf",
    "otf": "font/otf",
}


@dataclass(frozen=True)
class Limits:
    max_uncompressed: int = 32 * 1024 * 1024
    max_files: int = 500
    max_file: int = 8 * 1024 * 1024
    max_ratio: int = 100
    max_json_depth: int = 32
    max_json_nodes: int = 20000
    max_json_string: int = 100_000
    max_name_length: int = 120


LIMITS = Limits()


class TransferError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def package_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_project(
    conn,
    project_id: int,
    workspace_id: int,
    upload_dir: Path,
    *,
    app_version: str = "0.0.0",
    limits: Limits | None = None,
) -> bytes:
    """Read one project in a read-only transaction and return the package bytes."""
    limits = limits or LIMITS
    previous = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        try:
            return _export_locked(conn, project_id, workspace_id, Path(upload_dir), app_version, limits)
        finally:
            conn.rollback()
    finally:
        try:
            conn.execute("PRAGMA query_only=OFF")
        finally:
            conn.isolation_level = previous


def preview_package(data: bytes, *, expected_sha256: str | None = None, limits: Limits | None = None) -> dict:
    parsed = _parse(data, expected_sha256=expected_sha256, limits=limits or LIMITS)
    return _preview_dict(parsed)


def import_project(
    conn,
    data: bytes,
    *,
    upload_dir: Path,
    workspace_id: int,
    user_id: int | None,
    enable_keys: set[str] | None = None,
    expected_sha256: str | None = None,
    fail_after: str | None = None,
    limits: Limits | None = None,
) -> dict:
    """Validate again, write one transaction, then move asset files into place."""
    limits = limits or LIMITS
    parsed = _parse(data, expected_sha256=expected_sha256, limits=limits)
    selected = set(enable_keys or ())
    known = {item["key"] for item in _automation_catalog(parsed)}
    unknown = sorted(selected - known)
    if unknown:
        raise TransferError("bad_enable", "要启用的项目不在作品包里")
    for key in selected:
        if not _ENABLE_KEY.match(key):
            raise TransferError("bad_enable", "要启用的项目不在作品包里")
    _integrity(parsed)

    upload_root = Path(upload_dir)
    upload_root.mkdir(parents=True, exist_ok=True)
    staging = upload_root / f".incoming-{secrets.token_hex(8)}"
    staging.mkdir(mode=0o700)
    staged_files: list[tuple[Path, str]] = []
    moved: list[Path] = []
    project_id = None
    previous = conn.isolation_level
    try:
        staged_files = _stage_assets(staging, parsed["assets"])
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        try:
            project_id = _insert_project(conn, parsed, int(workspace_id), user_id, selected)
            if fail_after == "project":
                raise TransferError("failpoint", "导入已中止")
            _insert_children(conn, parsed, project_id, staged_files, selected)
            for handle_path, _final_name in staged_files:
                _fsync(handle_path)
            commit_with_retry(conn)
        except Exception:
            conn.rollback()
            raise
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        conn.isolation_level = previous

    try:
        for source, final_name in staged_files:
            dest = upload_root / final_name
            os.replace(source, dest)
            moved.append(dest)
            try:
                os.chmod(dest, 0o600)
            except OSError:
                pass
        shutil.rmtree(staging, ignore_errors=True)
    except Exception as exc:
        _discard_project(conn, project_id, moved, staging)
        raise TransferError("write", "导入文件未能写入") from exc

    row = conn.execute("SELECT id, slug, name FROM builder_projects WHERE id=?", (project_id,)).fetchone()
    return {"project_id": int(row["id"]), "slug": row["slug"], "name": row["name"]}


def asset_content_type(name: str) -> str | None:
    match = re.fullmatch(r"[a-f0-9]{16}\.(png|jpg|gif|webp|woff|woff2|ttf|otf)", name or "")
    if not match:
        return None
    return _ASSET_TYPES[match.group(1)]


def _export_locked(conn, project_id: int, workspace_id: int, upload_dir: Path, app_version: str, limits: Limits) -> bytes:
    project = conn.execute(
        "SELECT * FROM builder_projects WHERE id=? AND workspace_id=?",
        (project_id, workspace_id),
    ).fetchone()
    if not project:
        raise TransferError("not_found", "项目不存在")
    content, assets, omitted = _snapshot(conn, project, upload_dir)
    urls: list[str] = []
    _collect_urls(_automation_blob(content), urls)
    redactions: list[dict] = []
    content = _redact(content, "", redactions)
    files = _content_files(content, redactions, omitted, _unique(urls), project, app_version)
    _check_limits(files, assets, limits)
    return _zip_bytes({**files, **assets})


def _snapshot(conn, project, upload_dir: Path):
    project_id = int(project["id"])
    settings = _loads(project["settings"], {})
    body = {
        "project": {
            "name": project["name"],
            "slug": project["slug"],
            "kind": project["kind"],
            "description": project["description"] or "",
            "settings": settings if isinstance(settings, dict) else {},
            "enabled_capabilities": _loads(project["enabled_capabilities"], []),
            "theme_reference": project["theme_reference"] or "",
        },
        "surfaces": [],
        "documents": [],
        "routes": [],
        "entries": [],
        "bindings": [],
        "definitions": [],
        "instances": [],
        "models": [],
        "actions": [],
        "interactions": [],
        "conditions": [],
        "tokens": [],
        "variables": [],
    }
    surface_keys = {}
    for row in conn.execute("SELECT * FROM builder_surfaces WHERE project_id=? ORDER BY sort_order, id", (project_id,)):
        surface_keys[int(row["id"])] = row["surface_key"]
        body["surfaces"].append({
            "surface_key": row["surface_key"],
            "name": row["name"],
            "type": row["type"],
            "audience": row["audience"],
            "base_path": row["base_path"] or "",
            "settings": _loads(row["settings"], {}),
            "sort_order": row["sort_order"],
        })
    document_keys = {}
    documents = list(conn.execute(
        "SELECT * FROM builder_documents WHERE project_id=? ORDER BY sort_order, id", (project_id,)
    ))
    nodes_by_document: dict[int, list] = {}
    if documents:
        marks = ",".join("?" for _ in documents)
        ids = [int(row["id"]) for row in documents]
        for node in conn.execute(
            f"SELECT * FROM builder_nodes WHERE document_id IN ({marks}) ORDER BY sort_order, id",
            ids,
        ):
            nodes_by_document.setdefault(int(node["document_id"]), []).append({
                "node_key": node["node_key"],
                "parent_key": node["parent_key"],
                "component_type": node["component_type"],
                "props": _loads(node["props"], {}),
                "styles": _loads(node["styles"], {}),
                "responsive": _loads(node["responsive"], {}),
                "translations": _loads(node["translations"], {}),
                "sort_order": node["sort_order"],
            })
    for row in documents:
        document_keys[int(row["id"])] = row["document_key"]
        body["documents"].append({
            "document_key": row["document_key"],
            "surface_key": surface_keys.get(row["surface_id"]) or "",
            "name": row["name"],
            "type": row["type"] or "page",
            "route": row["route"] or "",
            "sort_order": row["sort_order"],
            "schema": _loads(row["schema"], {}),
            "nodes": nodes_by_document.get(int(row["id"]), []),
        })
    for row in conn.execute("SELECT * FROM builder_route_ownership WHERE project_id=? ORDER BY id", (project_id,)):
        body["routes"].append({
            "document_key": document_keys.get(int(row["document_id"]), ""),
            "surface_key": surface_keys.get(int(row["surface_id"]), ""),
            "route": row["route"] or "",
            "renderer_type": row["renderer_type"] or "native",
            "configuration": _loads(row["configuration"], {}),
        })
    for row in conn.execute("SELECT * FROM builder_entry_points WHERE project_id=? ORDER BY id", (project_id,)):
        body["entries"].append({
            "document_key": document_keys.get(row["document_id"]) or "",
            "surface_key": surface_keys.get(row["surface_id"]) or "",
            "entry_type": row["entry_type"],
            "entry_key": row["entry_key"],
            "configuration": _loads(row["configuration"], {}),
        })
    for row in conn.execute("SELECT * FROM builder_bindings WHERE project_id=? ORDER BY id", (project_id,)):
        body["bindings"].append({
            "document_key": document_keys.get(row["document_id"]) or "",
            "node_key": row["node_key"] or "",
            "binding_key": row["binding_key"],
            "source_type": row["source_type"],
            "source_config": _loads(row["source_config"], {}),
            "transform": _loads(row["transform"], {}),
        })
    definition_keys = {}
    for row in conn.execute("SELECT * FROM builder_component_definitions WHERE project_id=? ORDER BY id", (project_id,)):
        definition_keys[int(row["id"])] = row["component_key"]
        body["definitions"].append({
            "component_key": row["component_key"],
            "name": row["name"],
            "description": row["description"] or "",
            "version": row["version"],
            "root_structure": _loads(row["root_structure"], []),
            "property_schema": _loads(row["property_schema"], {}),
            "slots": _loads(row["slots"], {}),
            "variants": _loads(row["variants"], {}),
            "default_variant": row["default_variant"] or "default",
            "data_inputs": _loads(row["data_inputs"], {}),
            "events": _loads(row["events"], []),
            "token_dependencies": _loads(row["token_dependencies"], []),
            "metadata": _loads(row["metadata"], {}),
        })
    for row in conn.execute("SELECT * FROM builder_component_instances WHERE project_id=? ORDER BY id", (project_id,)):
        body["instances"].append({
            "document_key": document_keys.get(int(row["document_id"]), ""),
            "node_key": row["node_key"],
            "component_key": definition_keys.get(int(row["component_definition_id"]), ""),
            "variant": row["variant"] or "default",
            "overrides": _loads(row["overrides"], {}),
            "slot_content": _loads(row["slot_content"], {}),
            "bindings": _loads(row["bindings"], {}),
        })
    for row in conn.execute("SELECT * FROM builder_data_models WHERE project_id=? ORDER BY id", (project_id,)):
        body["models"].append({
            "model_key": row["model_key"],
            "name": row["name"],
            "schema": _loads(row["schema"], {}),
            "adapter": row["adapter"] or "native",
        })
    for row in conn.execute("SELECT * FROM builder_actions WHERE project_id=? ORDER BY sort_order, id", (project_id,)):
        body["actions"].append({
            "action_key": row["action_key"],
            "document_key": document_keys.get(row["document_id"]) or "",
            "node_key": row["node_key"] or "",
            "event_type": row["event_type"],
            "action_type": row["action_type"],
            "configuration": _loads(row["configuration"], {}),
            "sort_order": row["sort_order"],
        })
    for row in conn.execute("SELECT * FROM builder_interactions WHERE project_id=? ORDER BY id", (project_id,)):
        body["interactions"].append({
            "interaction_key": row["interaction_key"],
            "document_key": document_keys.get(row["document_id"]) or "",
            "node_key": row["node_key"] or "",
            "trigger_type": row["trigger_type"],
            "interaction_type": row["interaction_type"],
            "configuration": _loads(row["configuration"], {}),
        })
    for row in conn.execute("SELECT * FROM builder_conditions WHERE project_id=? ORDER BY id", (project_id,)):
        body["conditions"].append({
            "condition_key": row["condition_key"],
            "name": row["name"],
            "expression": _loads(row["expression"], {}),
        })
    for row in conn.execute("SELECT * FROM builder_design_tokens WHERE project_id=? ORDER BY id", (project_id,)):
        body["tokens"].append({
            "token_key": row["token_key"],
            "name": row["name"],
            "category": row["category"],
            "group_name": row["group_name"] or "",
            "values_json": _loads(row["values_json"], {}),
            "description": row["description"] or "",
        })
    for row in conn.execute("SELECT * FROM builder_project_variables WHERE project_id=? ORDER BY id", (project_id,)):
        body["variables"].append({
            "variable_key": row["variable_key"],
            "name": row["name"],
            "value_json": _loads(row["value_json"], None),
            "value_type": row["value_type"] or "string",
            "group_name": row["group_name"] or "",
        })
    omitted = {
        "data_records": _count(conn, "builder_data_records", project_id),
        "deployments": _count(conn, "builder_deployments", project_id),
        "runtime_events": _count(conn, "builder_runtime_events", project_id),
        "revisions": _count(conn, "builder_project_revisions", project_id),
        "installations": _count(conn, "builder_package_installations", project_id),
    }
    assets: dict[str, bytes] = {}
    mapping: dict[str, str] = {}
    body = _rewrite_assets(body, upload_dir, assets, mapping)
    return body, assets, omitted


def _content_files(content, redactions, omitted, urls, project, app_version: str) -> dict[str, bytes]:
    name = _clean_name(content["project"].get("name"))
    files = {
        "manifest.json": _dump({
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "app_version": str(app_version or "0.0.0")[:40],
            "project_id": str(project["id"]),
            "project_name": name,
            "requires": [],
            "migrations": [],
        }),
        "content/project.json": _dump(content["project"]),
        "content/pages.json": _dump({
            "surfaces": content["surfaces"],
            "documents": [item for item in content["documents"] if item.get("type") != "workflow"],
            "routes": content["routes"],
            "entries": content["entries"],
            "bindings": content["bindings"],
        }),
        "content/components.json": _dump({
            "definitions": content["definitions"],
            "instances": content["instances"],
        }),
        "content/collections.json": _dump(content["models"]),
        "content/workflows.json": _dump({
            "documents": [item for item in content["documents"] if item.get("type") == "workflow"],
            "actions": content["actions"],
            "interactions": content["interactions"],
            "conditions": content["conditions"],
        }),
        "content/design.json": _dump({"tokens": content["tokens"], "variables": content["variables"]}),
        "content/redactions.json": _dump(redactions),
        "content/omitted.json": _dump(omitted),
        "content/external_urls.json": _dump(urls),
    }
    return {name: text.encode("utf-8") for name, text in files.items()}


def _parse(data: bytes, *, expected_sha256: str | None, limits: Limits) -> dict:
    digest = package_sha256(data)
    if expected_sha256:
        wanted = expected_sha256.strip().lower()
        if len(wanted) != 64 or not re.fullmatch(r"[0-9a-f]{64}", wanted):
            raise TransferError("hash", "作品包内容与校验值不一致")
        if not hmac.compare_digest(digest, wanted):
            raise TransferError("hash", "作品包内容与校验值不一致")
    members = _read_zip(data, limits)
    loaded = {name: _load_member(blob, limits) for name, blob in members.items() if name.endswith(".json")}
    _verify_checksums(members, loaded["checksums.json"])
    _validate_manifest(loaded["manifest.json"])
    content = _assemble(loaded)
    content["assets"] = {name: blob for name, blob in members.items() if name.startswith("assets/")}
    for name, blob in content["assets"].items():
        sniffed = _sniff_asset(blob)
        if not name.endswith("." + sniffed):
            raise TransferError("asset_type", "资源类型与内容不一致")
    urls: list[str] = []
    _collect_urls(_automation_blob(content), urls)
    for item in content["external_urls"]:
        if isinstance(item, str):
            cleaned = _sanitize_url(item)
            if cleaned:
                urls.append(cleaned)
    automations = _automation_catalog(content)
    redactions: list[dict] = []
    redacted = _redact({key: value for key, value in content.items() if key != "assets"}, "", redactions)
    redacted["assets"] = content["assets"]
    redacted["external_urls"] = _unique(urls)
    redacted["automations"] = automations
    redacted["redactions"] = _merge_redactions(content.get("packaged_redactions") or [], redactions)
    redacted["sha256"] = digest
    redacted["manifest"] = loaded["manifest.json"]
    return redacted


def _assemble(loaded: dict) -> dict:
    project = loaded["content/project.json"]
    pages = loaded.get("content/pages.json") or {}
    components = loaded.get("content/components.json") or {}
    workflows = loaded.get("content/workflows.json") or {}
    design = loaded.get("content/design.json") or {}
    if not isinstance(project, dict):
        raise TransferError("json", "project.json 必须是对象")
    for label, value in (
        ("pages", pages), ("components", components), ("workflows", workflows), ("design", design),
    ):
        if not isinstance(value, dict):
            raise TransferError("json", f"{label} 的结构无效")
    models = loaded.get("content/collections.json")
    if models is None:
        models = []
    if not isinstance(models, list):
        raise TransferError("json", "collections.json 必须是数组")
    documents = _as_list(pages.get("documents")) + _as_list(workflows.get("documents"))
    content = {
        "project": project,
        "surfaces": _as_list(pages.get("surfaces")),
        "documents": documents,
        "routes": _as_list(pages.get("routes")),
        "entries": _as_list(pages.get("entries")),
        "bindings": _as_list(pages.get("bindings")),
        "definitions": _as_list(components.get("definitions")),
        "instances": _as_list(components.get("instances")),
        "models": models,
        "actions": _as_list(workflows.get("actions")),
        "interactions": _as_list(workflows.get("interactions")),
        "conditions": _as_list(workflows.get("conditions")),
        "tokens": _as_list(design.get("tokens")),
        "variables": _as_list(design.get("variables")),
        "external_urls": _as_list(loaded.get("content/external_urls.json")),
        "packaged_redactions": _as_list(loaded.get("content/redactions.json")),
        "omitted": loaded.get("content/omitted.json") if isinstance(loaded.get("content/omitted.json"), dict) else {},
    }
    _require_keys(content)
    return content


def _require_keys(content: dict) -> None:
    for collection, field in (
        ("surfaces", "surface_key"),
        ("documents", "document_key"),
        ("models", "model_key"),
        ("definitions", "component_key"),
        ("actions", "action_key"),
        ("interactions", "interaction_key"),
        ("conditions", "condition_key"),
        ("entries", "entry_key"),
    ):
        seen = set()
        for item in content[collection]:
            if not isinstance(item, dict):
                raise TransferError("json", "作品包结构无效")
            key = item.get(field) or ""
            if not _KEY.match(str(key)):
                raise TransferError("bad_key", "作品包里有无效的标识")
            if key in seen:
                raise TransferError("bad_key", "作品包里有重复的标识")
            seen.add(key)
    for collection, field in (("tokens", "token_key"), ("variables", "variable_key")):
        seen = set()
        for item in content[collection]:
            if not isinstance(item, dict):
                raise TransferError("json", "作品包结构无效")
            key = item.get(field) or ""
            if not _TOKEN_KEY.match(str(key)):
                raise TransferError("bad_key", "作品包里有无效的标识")
            if key in seen:
                raise TransferError("bad_key", "作品包里有重复的标识")
            seen.add(key)
    for item in content["bindings"]:
        if not isinstance(item, dict) or not _KEY.match(str(item.get("binding_key") or "")):
            raise TransferError("bad_key", "作品包里有无效的标识")
    for doc in content["documents"]:
        seen_nodes = set()
        for node in _as_list(doc.get("nodes")):
            if not isinstance(node, dict) or not _KEY.match(str(node.get("node_key") or "")):
                raise TransferError("bad_key", "作品包里有无效的标识")
            if node["node_key"] in seen_nodes:
                raise TransferError("bad_key", "作品包里有重复的标识")
            seen_nodes.add(node["node_key"])
        route = doc.get("route") or ""
        if route and (not _ROUTE.match(route) or ".." in route):
            raise TransferError("bad_route", "作品包里有无效的路径")


def _integrity(content: dict) -> None:
    surfaces = {item["surface_key"] for item in content["surfaces"]}
    documents: dict[str, dict] = {}
    nodes_by_doc: dict[str, set] = {}
    routes = set()
    for doc in content["documents"]:
        key = doc["document_key"]
        documents[key] = doc
        surface_key = doc.get("surface_key") or ""
        if surface_key and surface_key not in surfaces:
            _dangling()
        node_keys = {node["node_key"] for node in _as_list(doc.get("nodes"))}
        nodes_by_doc[key] = node_keys
        for node in _as_list(doc.get("nodes")):
            parent = node.get("parent_key")
            if parent and parent not in node_keys:
                _dangling()
            props = node.get("props") if isinstance(node.get("props"), dict) else {}
            target_model = props.get("target_model") or ""
            if target_model and target_model not in {item["model_key"] for item in content["models"]}:
                _dangling()
            for field in ("href", "url", "target", "path"):
                _check_internal(props.get(field), documents)
        route = doc.get("route") or ""
        if route:
            routes.add(route)
    models = {item["model_key"] for item in content["models"]}
    components = {item["component_key"]: item for item in content["definitions"]}
    actions = {item["action_key"] for item in content["actions"]}
    seen_routes = set()
    for route in content["routes"]:
        if not isinstance(route, dict) or route.get("document_key") not in documents:
            _dangling()
        surface_key = route.get("surface_key") or ""
        if not surface_key or surface_key not in surfaces:
            _dangling()
        route_path = route.get("route") or ""
        if route_path and route_path in seen_routes:
            raise TransferError("bad_route", "作品包里有重复的路径")
        if route_path:
            seen_routes.add(route_path)
        _check_internal(route.get("route"), documents)
    for entry in content["entries"]:
        document_key = entry.get("document_key") or ""
        if document_key and document_key not in documents:
            _dangling()
        surface_key = entry.get("surface_key") or ""
        if surface_key and surface_key not in surfaces:
            _dangling()
    for binding in content["bindings"]:
        document_key = binding.get("document_key") or ""
        node_key = binding.get("node_key") or ""
        if document_key and document_key not in documents:
            _dangling()
        if node_key:
            if document_key and node_key not in nodes_by_doc.get(document_key, ()):
                _dangling()
            if not document_key and not any(node_key in keys for keys in nodes_by_doc.values()):
                _dangling()
        config = binding.get("source_config") if isinstance(binding.get("source_config"), dict) else {}
        model_key = config.get("model_key") or ""
        if model_key and model_key not in models:
            _dangling()
        if (binding.get("source_type") == "collection") and model_key not in models:
            _dangling()
        if config.get("document_key") and config["document_key"] not in documents:
            _dangling()
    for action in content["actions"]:
        _check_ref(action, documents, nodes_by_doc, models, components, actions)
    for interaction in content["interactions"]:
        _check_ref(interaction, documents, nodes_by_doc, models, components, actions)
    for condition in content["conditions"]:
        _check_ref(condition.get("expression"), documents, nodes_by_doc, models, components, actions)
    for instance in content["instances"]:
        if not isinstance(instance, dict):
            _dangling()
        component = components.get(instance.get("component_key"))
        document_key = instance.get("document_key") or ""
        node_key = instance.get("node_key") or ""
        if not component or document_key not in documents or node_key not in nodes_by_doc.get(document_key, ()):
            _dangling()
        _check_overrides(component, instance.get("overrides"))
    for token in content["tokens"]:
        if not isinstance(token, dict) or not token.get("token_key"):
            _dangling()
    _ = routes


def _check_ref(value, documents, nodes_by_doc, models, components, actions) -> None:
    if isinstance(value, dict):
        document_key = value.get("document_key") or value.get("target_document") or ""
        node_key = value.get("node_key") or value.get("target_node") or ""
        if document_key and document_key not in documents:
            _dangling()
        if node_key:
            if document_key and node_key not in nodes_by_doc.get(document_key, ()):
                _dangling()
            elif not document_key and not any(node_key in keys for keys in nodes_by_doc.values()):
                _dangling()
        model_key = value.get("model_key") or value.get("target_model") or ""
        if model_key and model_key not in models:
            _dangling()
        component_key = value.get("component_key") or ""
        if component_key and component_key not in components:
            _dangling()
        if "action_key" in value and "event_type" not in value and value.get("action_key") not in actions:
            _dangling()
        for field in ("href", "url", "target", "path"):
            _check_internal(value.get(field), documents)
        for item in value.values():
            if isinstance(item, (dict, list)):
                _check_ref(item, documents, nodes_by_doc, models, components, actions)
    elif isinstance(value, list):
        for item in value:
            _check_ref(item, documents, nodes_by_doc, models, components, actions)


def _check_overrides(component: dict, overrides) -> None:
    if not overrides:
        return
    if not isinstance(overrides, dict):
        _dangling()
    schema = component.get("property_schema") if isinstance(component.get("property_schema"), dict) else {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    structure_keys = _structure_keys(component.get("root_structure"))
    for key, _value in overrides.items():
        exposure = properties.get(key)
        if not isinstance(exposure, dict):
            _dangling()
        node_key = exposure.get("node_key") or ""
        if node_key not in structure_keys:
            _dangling()


def _structure_keys(structure) -> set:
    found = set()
    if isinstance(structure, list):
        for item in structure:
            if isinstance(item, dict):
                key = item.get("key") or item.get("node_key")
                if key:
                    found.add(str(key))
                found |= _structure_keys(item.get("children"))
    elif isinstance(structure, dict):
        key = structure.get("key") or structure.get("node_key")
        if key:
            found.add(str(key))
        found |= _structure_keys(structure.get("children"))
    return found


def _check_internal(value, documents: dict) -> None:
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("/uploads/") or value.startswith("/static/"):
        return
    if value.startswith("asset:"):
        return
    routes = {(doc.get("route") or "") for doc in documents.values()}
    if value not in routes:
        _dangling()


def _dangling() -> None:
    raise TransferError("dangling", "作品包里有无法对应的引用，已取消导入")


def _insert_project(conn, content: dict, workspace_id: int, user_id: int | None, _selected: set[str]) -> int:
    project = content["project"] if isinstance(content["project"], dict) else {}
    name = _clean_name(project.get("name") or content["manifest"].get("project_name"))
    slug = _allocate_slug(conn, workspace_id, name)
    settings = project.get("settings") if isinstance(project.get("settings"), dict) else {}
    settings = {
        key: value
        for key, value in settings.items()
        if key != "imported_from"
    }
    settings["imported_from"] = {
        "package_sha256": content["sha256"],
        "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    now = _now()
    cursor = conn.execute(
        """INSERT INTO builder_projects
           (workspace_id, name, slug, kind, status, description, settings, schema_version,
            enabled_capabilities, theme_reference, created_by, updated_at)
           VALUES (?, ?, ?, ?, 'draft', ?, ?, 1, ?, ?, ?, ?)""",
        (
            workspace_id,
            name,
            slug,
            _clean_kind(project.get("kind")),
            _clean_text(project.get("description") or "", 2000),
            _dump(settings),
            _dump(project.get("enabled_capabilities") if isinstance(project.get("enabled_capabilities"), list) else []),
            _clean_text(project.get("theme_reference") or "", 200),
            user_id,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _insert_children(conn, content: dict, project_id: int, staged_files: list[tuple[Path, str]], selected: set[str]) -> None:
    pointers = {}
    members = list(content["assets"].keys())
    if len(members) != len(staged_files):
        raise TransferError("write", "导入文件未能写入")
    for member, (_path, final_name) in zip(members, staged_files):
        pointers[member] = f"/uploads/{final_name}"
    content = _bind_assets(content, pointers)
    now = _now()
    surface_ids = {}
    for index, item in enumerate(content["surfaces"]):
        cursor = conn.execute(
            """INSERT INTO builder_surfaces
               (project_id, surface_key, name, type, audience, base_path, settings, sort_order, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id, item["surface_key"], _clean_text(item.get("name") or item["surface_key"], 120),
                _clean_text(item.get("type") or "public_web", 40),
                _clean_text(item.get("audience") or "public", 40),
                _clean_text(item.get("base_path") or "", 200),
                _dump(item.get("settings") if isinstance(item.get("settings"), dict) else {}),
                int(item.get("sort_order") or index), now,
            ),
        )
        surface_ids[item["surface_key"]] = int(cursor.lastrowid)
    document_ids = {}
    for index, item in enumerate(content["documents"]):
        is_workflow = item.get("type") == "workflow"
        enabled = f"workflow:{item['document_key']}" in selected
        status = "active" if (not is_workflow or enabled) else "disabled"
        cursor = conn.execute(
            """INSERT INTO builder_documents
               (project_id, surface_id, document_key, name, type, route, status, schema, sort_order, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                surface_ids.get(item.get("surface_key") or ""),
                item["document_key"],
                _clean_text(item.get("name") or item["document_key"], 120),
                "workflow" if is_workflow else _clean_text(item.get("type") or "page", 40),
                item.get("route") or "",
                status,
                _dump(item.get("schema") if isinstance(item.get("schema"), dict) else {}),
                int(item.get("sort_order") or index),
                now,
            ),
        )
        document_id = int(cursor.lastrowid)
        document_ids[item["document_key"]] = document_id
        for node_index, node in enumerate(_as_list(item.get("nodes"))):
            conn.execute(
                """INSERT INTO builder_nodes
                   (document_id, node_key, parent_key, component_type, props, styles, responsive, translations, sort_order, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    document_id,
                    node["node_key"],
                    node.get("parent_key") or None,
                    _clean_text(node.get("component_type") or "text", 40),
                    _dump(node.get("props") if isinstance(node.get("props"), dict) else {}),
                    _dump(node.get("styles") if isinstance(node.get("styles"), dict) else {}),
                    _dump(node.get("responsive") if isinstance(node.get("responsive"), dict) else {}),
                    _dump(node.get("translations") if isinstance(node.get("translations"), dict) else {}),
                    int(node.get("sort_order") or node_index),
                    now,
                ),
            )
    for item in content["routes"]:
        document_id = document_ids.get(item.get("document_key"))
        surface_id = surface_ids.get(item.get("surface_key") or "")
        if not document_id or not surface_id:
            _dangling()
        conn.execute(
            """INSERT INTO builder_route_ownership
               (project_id, surface_id, document_id, route, renderer_type, configuration, status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'draft', ?)""",
            (
                project_id, surface_id, document_id, item.get("route") or "",
                _clean_text(item.get("renderer_type") or "native", 40),
                _dump(item.get("configuration") if isinstance(item.get("configuration"), dict) else {}),
                now,
            ),
        )
    for item in content["entries"]:
        enabled = f"entry:{item['entry_key']}" in selected
        entry_type = _clean_text(item.get("entry_type") or "route", 40)
        stored_key = f"{item['entry_key']}-{project_id}"
        while conn.execute(
            "SELECT 1 FROM builder_entry_points WHERE entry_type=? AND entry_key=?",
            (entry_type, stored_key),
        ).fetchone():
            stored_key = f"{stored_key}-2"
        conn.execute(
            """INSERT INTO builder_entry_points
               (project_id, surface_id, document_id, entry_type, entry_key, configuration, status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                surface_ids.get(item.get("surface_key") or ""),
                document_ids.get(item.get("document_key") or ""),
                entry_type,
                stored_key,
                _dump(item.get("configuration") if isinstance(item.get("configuration"), dict) else {}),
                "active" if enabled else "disabled",
                now,
            ),
        )
    for item in content["models"]:
        conn.execute(
            """INSERT INTO builder_data_models (project_id, model_key, name, schema, adapter, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                project_id, item["model_key"], _clean_text(item.get("name") or item["model_key"], 120),
                _dump(item.get("schema") if isinstance(item.get("schema"), dict) else {}),
                _clean_text(item.get("adapter") or "native", 40), now,
            ),
        )
    for item in content["bindings"]:
        conn.execute(
            """INSERT INTO builder_bindings
               (project_id, document_id, node_key, binding_key, source_type, source_config, transform, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                document_ids.get(item.get("document_key") or ""),
                item.get("node_key") or None,
                item["binding_key"],
                _clean_text(item.get("source_type") or "literal", 40),
                _dump(item.get("source_config") if isinstance(item.get("source_config"), dict) else {}),
                _dump(item.get("transform") if isinstance(item.get("transform"), dict) else {}),
                now,
            ),
        )
    definition_ids = {}
    for item in content["definitions"]:
        cursor = conn.execute(
            """INSERT INTO builder_component_definitions
               (project_id, component_key, name, description, version, root_structure, property_schema, slots,
                variants, default_variant, data_inputs, events, token_dependencies, metadata, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id, item["component_key"], _clean_text(item.get("name") or item["component_key"], 120),
                _clean_text(item.get("description") or "", 2000), int(item.get("version") or 1),
                _dump(item.get("root_structure") if isinstance(item.get("root_structure"), list) else []),
                _dump(item.get("property_schema") if isinstance(item.get("property_schema"), dict) else {}),
                _dump(item.get("slots") if isinstance(item.get("slots"), dict) else {}),
                _dump(item.get("variants") if isinstance(item.get("variants"), dict) else {}),
                _clean_text(item.get("default_variant") or "default", 40),
                _dump(item.get("data_inputs") if isinstance(item.get("data_inputs"), dict) else {}),
                _dump(item.get("events") if isinstance(item.get("events"), list) else []),
                _dump(item.get("token_dependencies") if isinstance(item.get("token_dependencies"), list) else []),
                _dump(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                now,
            ),
        )
        definition_ids[item["component_key"]] = int(cursor.lastrowid)
    for item in content["instances"]:
        conn.execute(
            """INSERT INTO builder_component_instances
               (project_id, document_id, node_key, component_definition_id, variant, overrides, slot_content, bindings, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id, document_ids[item["document_key"]], item["node_key"],
                definition_ids[item["component_key"]], _clean_text(item.get("variant") or "default", 40),
                _dump(item.get("overrides") if isinstance(item.get("overrides"), dict) else {}),
                _dump(item.get("slot_content") if isinstance(item.get("slot_content"), dict) else {}),
                _dump(item.get("bindings") if isinstance(item.get("bindings"), dict) else {}),
                now,
            ),
        )
    for item in content["actions"]:
        enabled = f"action:{item['action_key']}" in selected
        configuration = item.get("configuration") if isinstance(item.get("configuration"), dict) else {}
        configuration = dict(configuration)
        configuration["enabled"] = enabled
        conn.execute(
            """INSERT INTO builder_actions
               (project_id, document_id, node_key, action_key, event_type, action_type, configuration, sort_order, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id, document_ids.get(item.get("document_key") or ""), item.get("node_key") or None,
                item["action_key"], _clean_text(item.get("event_type") or "click", 40),
                _clean_text(item.get("action_type") or "open", 40), _dump(configuration),
                int(item.get("sort_order") or 0), now,
            ),
        )
    for item in content["interactions"]:
        enabled = f"interaction:{item['interaction_key']}" in selected
        configuration = item.get("configuration") if isinstance(item.get("configuration"), dict) else {}
        configuration = dict(configuration)
        configuration["enabled"] = enabled
        conn.execute(
            """INSERT INTO builder_interactions
               (project_id, document_id, node_key, interaction_key, trigger_type, interaction_type, configuration, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id, document_ids.get(item.get("document_key") or ""), item.get("node_key") or None,
                item["interaction_key"], _clean_text(item.get("trigger_type") or "click", 40),
                _clean_text(item.get("interaction_type") or "fade", 40), _dump(configuration), now,
            ),
        )
    for item in content["conditions"]:
        conn.execute(
            """INSERT INTO builder_conditions (project_id, condition_key, name, expression)
               VALUES (?, ?, ?, ?)""",
            (
                project_id, item["condition_key"], _clean_text(item.get("name") or item["condition_key"], 120),
                _dump(item.get("expression") if isinstance(item.get("expression"), (dict, list)) else {}),
            ),
        )
    for item in content["tokens"]:
        conn.execute(
            """INSERT INTO builder_design_tokens
               (project_id, token_key, name, category, group_name, values_json, description, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id, item["token_key"], _clean_text(item.get("name") or item["token_key"], 120),
                _clean_text(item.get("category") or "color", 40), _clean_text(item.get("group_name") or "", 80),
                _dump(item.get("values_json") if isinstance(item.get("values_json"), dict) else {}),
                _clean_text(item.get("description") or "", 500), now,
            ),
        )
    for item in content["variables"]:
        conn.execute(
            """INSERT INTO builder_project_variables
               (project_id, variable_key, name, value_json, value_type, group_name, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id, item["variable_key"], _clean_text(item.get("name") or item["variable_key"], 120),
                _dump(item.get("value_json")), _clean_text(item.get("value_type") or "string", 40),
                _clean_text(item.get("group_name") or "", 80), now,
            ),
        )


def _stage_assets(staging: Path, assets: dict[str, bytes]) -> list[tuple[Path, str]]:
    staged = []
    used = set()
    for member, blob in assets.items():
        ext = _sniff_asset(blob)
        for _attempt in range(5):
            final_name = f"{secrets.token_hex(8)}.{ext}"
            if final_name not in used:
                break
        else:
            raise TransferError("write", "导入文件未能写入")
        used.add(final_name)
        path = staging / final_name
        path.write_bytes(blob)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        staged.append((path, final_name))
    return staged


def _discard_project(conn, project_id: int | None, moved: list[Path], staging: Path) -> None:
    try:
        if project_id is not None:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM builder_projects WHERE id=?", (project_id,))
            commit_with_retry(conn)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    for path in moved:
        try:
            path.unlink()
        except OSError:
            pass
    shutil.rmtree(staging, ignore_errors=True)


def _allocate_slug(conn, workspace_id: int, name: str) -> str:
    base = (_slug(name) or "project")[:60]
    slug = base
    number = 2
    while conn.execute(
        "SELECT 1 FROM builder_projects WHERE workspace_id=? AND slug=?",
        (workspace_id, slug),
    ).fetchone():
        slug = f"{base}-{number}"
        number += 1
        if number > 10000:
            raise TransferError("slug", "无法分配作品地址")
    return slug


def _preview_dict(content: dict) -> dict:
    pages = [item for item in content["documents"] if item.get("type") != "workflow"]
    ignored = []
    omitted = content.get("omitted") if isinstance(content.get("omitted"), dict) else {}
    for key, label in _OMITTED_LABELS.items():
        try:
            count = int(omitted.get(key) or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            ignored.append(f"{label}（{count} 条未导入）")
    ignored.append(_ALWAYS_IGNORED)
    hint = content.get("manifest", {}).get("project_id")
    return {
        "package_sha256": content["sha256"],
        "project_name": _clean_name((content.get("project") or {}).get("name") or content.get("manifest", {}).get("project_name")),
        "source_hint": str(hint)[:80] if hint is not None else "",
        "page_count": len(pages),
        "collection_count": len(content["models"]),
        "ignored": ignored,
        "needs_reconfiguration": content.get("redactions") or [],
        "automations": content.get("automations") or _automation_catalog(content),
        "external_urls": content.get("external_urls") or [],
        "warning": PREVIEW_WARNING,
    }


def _automation_catalog(content: dict) -> list[dict]:
    items = []
    for action in content["actions"]:
        items.append({
            "key": f"action:{action['action_key']}",
            "kind": "action",
            "name": action.get("action_key"),
            "external_urls": _urls_in(action),
        })
    for interaction in content["interactions"]:
        items.append({
            "key": f"interaction:{interaction['interaction_key']}",
            "kind": "interaction",
            "name": interaction.get("interaction_key"),
            "external_urls": _urls_in(interaction),
        })
    for doc in content["documents"]:
        if doc.get("type") == "workflow":
            items.append({
                "key": f"workflow:{doc['document_key']}",
                "kind": "workflow",
                "name": doc.get("name") or doc["document_key"],
                "external_urls": _urls_in(doc),
            })
    for entry in content["entries"]:
        items.append({
            "key": f"entry:{entry['entry_key']}",
            "kind": "entry",
            "name": entry.get("entry_key"),
            "external_urls": _urls_in(entry),
        })
    return items[:200]


def _automation_blob(content: dict) -> dict:
    return {
        "actions": content["actions"],
        "interactions": content["interactions"],
        "workflows": [item for item in content["documents"] if item.get("type") == "workflow"],
        "entries": content["entries"],
    }


def _read_zip(data: bytes, limits: Limits) -> dict[str, bytes]:
    if not data.startswith(b"PK"):
        raise TransferError("corrupt", "不是有效的作品包")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise TransferError("corrupt", "作品包已损坏") from exc
    seen: set[str] = set()
    seen_fold: set[str] = set()
    infos = archive.infolist()
    if len(infos) > limits.max_files:
        raise TransferError("too_many", "文件数量超过限制")
    for info in infos:
        if info.flag_bits & 0x1:
            raise TransferError("encrypted", "不能导入加密的压缩包")
    allowed = set(_CONTENT_FILES) | {"checksums.json"}
    for info in infos:
        _check_member(info, seen, seen_fold)
        name = info.filename
        if name not in allowed and not _ASSET_NAME.match(name):
            raise TransferError("bad_member", "包含不允许的文件")
    files: dict[str, bytes] = {}
    total = 0
    for info in infos:
        payload = _read_payload(archive, info, limits)
        if _looks_like_archive(payload):
            raise TransferError("nested_archive", "不能包含嵌套压缩包")
        total += len(payload)
        if total > limits.max_uncompressed:
            raise TransferError("too_large", "解压后总体积超过限制")
        files[info.filename] = payload
    missing = _REQUIRED - set(files)
    if missing:
        raise TransferError("bad_member", "作品包缺少必要文件")
    archive.close()
    return files


def _check_member(info: zipfile.ZipInfo, seen: set[str], seen_fold: set[str]) -> None:
    name = info.filename
    if info.flag_bits & 0x1:
        raise TransferError("encrypted", "不能导入加密的压缩包")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise TransferError("symlink", "不能包含符号链接")
    _reject_non_utf8(info)
    if not name or name.endswith("/") or "\\" in name or "\x00" in name:
        raise TransferError("bad_path", "包含不安全的路径")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise TransferError("bad_path", "包含不安全的路径")
    lowered = name.casefold()
    if lowered.endswith(_ARCHIVE_SUFFIXES):
        raise TransferError("nested_archive", "不能包含嵌套压缩包")
    for part in name.split("/"):
        if part in {"", ".", ".."}:
            raise TransferError("bad_path", "包含不安全的路径")
        if part.endswith(".") or part.endswith(" "):
            raise TransferError("bad_name", "文件名不合法")
        stem = part.split(".", 1)[0].upper()
        if stem in _RESERVED:
            raise TransferError("reserved_name", "文件名使用了系统保留名")
    if name in seen:
        raise TransferError("duplicate_name", "包含重复的文件名")
    if lowered in seen_fold:
        raise TransferError("case_conflict", "文件名在忽略大小写后冲突")
    seen.add(name)
    seen_fold.add(lowered)


def _reject_non_utf8(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x800:
        try:
            info.filename.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise TransferError("encoding", "文件名必须是 UTF-8") from exc
        return
    try:
        raw = info.filename.encode("cp437")
    except UnicodeEncodeError as exc:
        raise TransferError("encoding", "文件名必须是 UTF-8") from exc
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TransferError("encoding", "文件名必须是 UTF-8") from exc


def _read_payload(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limits: Limits) -> bytes:
    # file_size is the declared uncompressed size and is not trusted.
    if info.compress_size > limits.max_file:
        raise TransferError("too_large", "单文件超过限制")
    fp = getattr(archive, "fp", None)
    if fp is None:
        raise TransferError("corrupt", "作品包已损坏")
    fp.seek(info.header_offset)
    header = fp.read(30)
    if len(header) < 30 or header[:4] != b"PK\x03\x04":
        raise TransferError("corrupt", "作品包已损坏")
    name_len, extra_len = struct.unpack("<HH", header[26:30])
    flags = struct.unpack("<H", header[6:8])[0]
    if flags & 0x1:
        raise TransferError("encrypted", "不能导入加密的压缩包")
    fp.seek(info.header_offset + 30 + name_len + extra_len)
    compressed = fp.read(info.compress_size)
    if len(compressed) != info.compress_size:
        raise TransferError("corrupt", "作品包已损坏")
    if info.compress_type == zipfile.ZIP_STORED:
        data = compressed
    elif info.compress_type == zipfile.ZIP_DEFLATED:
        data = _inflate(compressed, limits)
    else:
        raise TransferError("bad_compression", "不支持的压缩方式")
    if len(data) > limits.max_file:
        raise TransferError("too_large", "单文件超过限制")
    return data


def _inflate(compressed: bytes, limits: Limits) -> bytes:
    # ZIP method 8 is raw deflate, without a zlib wrapper.
    decoder = zlib.decompressobj(-15)
    try:
        data = decoder.decompress(compressed, limits.max_file + 1)
        if len(data) <= limits.max_file:
            data += decoder.flush()
    except zlib.error as exc:
        raise TransferError("corrupt", "作品包已损坏") from exc
    if len(data) > limits.max_file or decoder.unconsumed_tail or not decoder.eof:
        raise TransferError("too_large", "解压后超过单文件上限")
    base = max(len(compressed), 1)
    if len(data) > base * limits.max_ratio:
        raise TransferError("ratio", "压缩比超过限制")
    return data


def _verify_checksums(files: dict[str, bytes], listed: Any) -> None:
    if not isinstance(listed, dict):
        raise TransferError("checksum", "校验和无效")
    expect = {name for name in files if name != "checksums.json"}
    if set(listed) != expect:
        raise TransferError("checksum", "校验和与文件不一致")
    for name, digest in listed.items():
        actual = hashlib.sha256(files[name]).hexdigest()
        if not isinstance(digest, str) or len(digest) != len(actual):
            raise TransferError("checksum", "校验和与文件不一致")
        if not hmac.compare_digest(actual, digest.lower()):
            raise TransferError("checksum", "校验和与文件不一致")


def _load_member(blob: bytes, limits: Limits) -> Any:
    if _looks_like_archive(blob):
        raise TransferError("nested_archive", "不能包含嵌套压缩包")
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TransferError("encoding", "JSON 必须是 UTF-8") from exc
    if text.startswith("\ufeff"):
        raise TransferError("encoding", "JSON 必须是 UTF-8")
    _scan_json(text, limits)
    try:
        value, end = json.JSONDecoder(object_pairs_hook=_reject_duplicate_keys).raw_decode(text)
    except TransferError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise TransferError("json", "JSON 结构无效") from exc
    if text[end:].strip():
        raise TransferError("json", "JSON 结构无效")
    return value


def _scan_json(text: str, limits: Limits) -> None:
    index = 0
    length = len(text)
    depth = 0
    nodes = 0

    def bump() -> None:
        nonlocal nodes
        nodes += 1
        if nodes > limits.max_json_nodes:
            raise TransferError("json_limit", "JSON 节点过多")

    while index < length:
        char = text[index]
        if char in " \r\n\t":
            index += 1
            continue
        if char == '"':
            index += 1
            size = 0
            while index < length:
                current = text[index]
                if current == "\\":
                    index += 2
                    size += 1
                elif current == '"':
                    index += 1
                    break
                else:
                    if ord(current) < 32:
                        raise TransferError("json", "JSON 结构无效")
                    index += 1
                    size += 1
                if size > limits.max_json_string:
                    raise TransferError("json_limit", "JSON 字符串过长")
            else:
                raise TransferError("json", "JSON 结构无效")
            bump()
            continue
        if char in "{[":
            depth += 1
            if depth > limits.max_json_depth:
                raise TransferError("json_limit", "JSON 嵌套过深")
            bump()
            index += 1
            continue
        if char in "}]":
            depth -= 1
            if depth < 0:
                raise TransferError("json", "JSON 结构无效")
            index += 1
            continue
        if char in ",:":
            index += 1
            continue
        if text.startswith("true", index) or text.startswith("null", index):
            index += 4
            bump()
            continue
        if text.startswith("false", index):
            index += 5
            bump()
            continue
        if char == "-" or char.isdigit():
            index += 1
            while index < length and text[index] in "0123456789.eE+-":
                index += 1
            bump()
            continue
        raise TransferError("json", "JSON 结构无效")
    if depth != 0:
        raise TransferError("json", "JSON 结构无效")


def _reject_duplicate_keys(pairs):
    keys = [key for key, _value in pairs]
    if len(keys) != len(set(keys)):
        raise TransferError("json", "JSON 对象有重复键")
    return dict(pairs)


def _validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise TransferError("schema_version", "无法识别的作品包")
    version = manifest.get("schema_version")
    if type(version) is not int:
        raise TransferError("schema_version", "无法识别的作品包")
    if version > SCHEMA_VERSION:
        raise TransferError("schema_version", "请升级应用后再导入这个作品包")
    if version != SCHEMA_VERSION:
        raise TransferError("schema_version", "无法识别的作品包")
    requires = manifest.get("requires")
    migrations = manifest.get("migrations")
    if not isinstance(requires, list) or not isinstance(migrations, list):
        raise TransferError("requires", "这个作品包需要当前版本没有的功能")
    if requires or migrations:
        raise TransferError("requires", "这个作品包需要当前版本没有的功能")


def _sniff_asset(data: bytes) -> str:
    if _looks_like_archive(data):
        raise TransferError("nested_archive", "不能包含嵌套压缩包")
    head = data[:256].lstrip().lower()
    if head.startswith(b"<svg") or head.startswith(b"<?xml") or head.startswith(b"<!doctype"):
        raise TransferError("svg", "不支持 SVG")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"wOFF"):
        return "woff"
    if data.startswith(b"wOF2"):
        return "woff2"
    if data.startswith(b"\x00\x01\x00\x00") or data.startswith(b"true") or data.startswith(b"typ1"):
        return "ttf"
    if data.startswith(b"OTTO"):
        return "otf"
    raise TransferError("asset_type", "资源只能是图片或字体")


def _looks_like_archive(data: bytes) -> bool:
    return (
        data.startswith(b"PK\x03\x04")
        or data.startswith(b"PK\x05\x06")
        or data.startswith(b"PK\x07\x08")
        or data.startswith(b"\x1f\x8b")
        or data.startswith(b"7z\xbc\xaf'\x1c")
        or data.startswith(b"Rar!\x1a\x07")
    )


def _rewrite_assets(value, upload_dir: Path, assets: dict[str, bytes], mapping: dict[str, str]):
    if isinstance(value, str):
        def replace(match):
            filename = match.group(1)
            if filename in mapping:
                return "asset:" + mapping[filename]
            path = _safe_upload(upload_dir, filename)
            if path is None:
                return ""
            blob = path.read_bytes()
            if len(blob) > LIMITS.max_file:
                return ""
            try:
                ext = _sniff_asset(blob)
            except TransferError:
                return ""
            member = f"assets/{secrets.token_hex(8)}.{ext}"
            assets[member] = blob
            mapping[filename] = member
            return "asset:" + member
        return _UPLOAD_URL.sub(replace, value)
    if isinstance(value, list):
        return [_rewrite_assets(item, upload_dir, assets, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_assets(item, upload_dir, assets, mapping) for key, item in value.items()}
    return value


def _safe_upload(upload_dir: Path, filename: str) -> Path | None:
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        return None
    root = upload_dir.resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file() or path.is_symlink():
        return None
    return path


def _bind_assets(value, pointers: dict[str, str]):
    if isinstance(value, str):
        if value.startswith("asset:"):
            member = value[6:]
            if member not in pointers:
                _dangling()
            return pointers[member]

        def replace(match):
            member = match.group(1)
            if member not in pointers:
                _dangling()
            return pointers[member]
        return _ASSET_POINTER.sub(replace, value)
    if isinstance(value, list):
        return [_bind_assets(item, pointers) for item in value]
    if isinstance(value, dict):
        return {key: _bind_assets(item, pointers) for key, item in value.items()}
    return value


def _redact(value, path: str, found: list[dict]):
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            if _is_secret_key(str(key)):
                found.append({"path": child, "label": REDACTED})
                output[key] = REDACTED
            else:
                output[key] = _redact(item, child, found)
        return output
    if isinstance(value, list):
        return [_redact(item, f"{path}[{index}]", found) for index, item in enumerate(value)]
    if isinstance(value, str) and path and _string_is_sensitive(value):
        found.append({"path": path, "label": REDACTED})
        return REDACTED
    return value


def _is_secret_key(key: str) -> bool:
    folded = re.sub(r"[^a-z0-9]", "", key.lower())
    if folded in {"tokenkey", "tokendependencies"}:
        return False
    if folded in _SECRET_FOLDED:
        return True
    return folded.endswith("apikey") or folded.endswith("password") or folded.endswith("secret") or folded.endswith("token")


def _string_is_sensitive(value: str) -> bool:
    if value == REDACTED:
        return False
    if _JWT.search(value) or _SK.search(value) or _BEARER.search(value):
        return True
    if _TOKEN_QUERY.search(value) or _WEBHOOK.search(value):
        return True
    if _RANDOM.match(value) and any(char.isdigit() for char in value) and any(char.isalpha() for char in value):
        return True
    return False


def _collect_urls(value, found: list[str]) -> None:
    if isinstance(value, str):
        for match in _URL_RE.finditer(value):
            cleaned = _sanitize_url(match.group(0))
            if cleaned:
                found.append(cleaned)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_urls(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_urls(item, found)


def _urls_in(value) -> list[str]:
    found: list[str] = []
    _collect_urls(value, found)
    return _unique(found)[:20]


def _sanitize_url(raw: str) -> str | None:
    text = raw.strip().rstrip(").,]}>\"'")
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname
    webhook = (
        "webhook" in host
        or host.endswith("hooks.slack.com")
        or "discord.com" in host
        or "discordapp.com" in host
    )
    if webhook:
        return f"{parsed.scheme}://{host}"
    query = []
    for key, val in parse_qsl(parsed.query, keep_blank_values=False):
        if key.lower() in {"token", "key", "secret", "password", "access_token", "signature"}:
            continue
        query.append((key, val))
    parts = []
    for segment in (parsed.path or "").split("/"):
        if _RANDOM.match(segment) and any(char.isdigit() for char in segment):
            return f"{parsed.scheme}://{host}"
        parts.append(segment)
    return urlunparse((parsed.scheme, host, "/".join(parts), "", urlencode(query), ""))


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    checksums = {
        name: hashlib.sha256(blob).hexdigest()
        for name, blob in files.items()
        if name != "checksums.json"
    }
    packed = dict(files)
    packed["checksums.json"] = _dump(checksums).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in sorted(packed):
            info = zipfile.ZipInfo(filename=name, date_time=(2026, 1, 1, 0, 0, 0))
            info.flag_bits |= 0x800
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, packed[name])
    return buffer.getvalue()


def _check_limits(files: dict[str, bytes], assets: dict[str, bytes], limits: Limits) -> None:
    everything = {**files, **assets}
    if len(everything) + 1 > limits.max_files:
        raise TransferError("too_many", "文件数量超过限制")
    total = 0
    for blob in everything.values():
        if len(blob) > limits.max_file:
            raise TransferError("too_large", "单文件超过限制")
        total += len(blob)
    if total > limits.max_uncompressed:
        raise TransferError("too_large", "解压后总体积超过限制")


def _merge_redactions(packaged: list, found: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for item in list(packaged) + found:
        if isinstance(item, dict):
            path = str(item.get("path") or "")
            if path and path not in seen:
                seen.add(path)
                merged.append({"path": path, "label": REDACTED})
        elif isinstance(item, str) and item not in seen:
            seen.add(item)
            merged.append({"path": item, "label": REDACTED})
    return merged


def _clean_name(value: Any, limit: int | None = None) -> str:
    return _clean_text(value, limit or LIMITS.max_name_length) or "未命名作品"


def _clean_text(value: Any, limit: int) -> str:
    text = "".join(char for char in str(value or "") if unicodedata.category(char) != "Cc")
    text = " ".join(text.split())
    return text[:limit].strip()


def _clean_kind(value: Any) -> str:
    text = str(value or "composition")
    if re.fullmatch(r"[a-z0-9_-]{1,40}", text):
        return text
    return "composition"


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _loads(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _unique(items: list[str]) -> list[str]:
    seen = set()
    output = []
    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def _count(conn, table: str, project_id: int) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE project_id=?", (project_id,)).fetchone()
    return int(row["c"])


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
