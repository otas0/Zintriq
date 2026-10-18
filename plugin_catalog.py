"""Official and reviewed third-party packs. Install is Desktop-only; /plugins is read-only."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

PACKS = (
    {"id": "official-scene", "name": "Scene", "summary": "Hierarchy, camera, light, gizmo tools.", "file": "scene.zintriq-plugin.json"},
    {"id": "official-node", "name": "Node graph", "summary": "Labeled nodes and wires.", "file": "node.zintriq-plugin.json"},
    {"id": "official-ui", "name": "UI", "summary": "Screen layout and theme.", "file": "ui.zintriq-plugin.json"},
    {"id": "official-animation", "name": "Animation", "summary": "Keys, easing, playhead.", "file": "animation.zintriq-plugin.json"},
    {"id": "official-shader", "name": "Shader", "summary": "Local GLSL compile log.", "file": "shader.zintriq-plugin.json"},
    {"id": "official-audio", "name": "Audio", "summary": "Clips, gain, tracks.", "file": "audio.zintriq-plugin.json"},
    {"id": "official-level", "name": "Level", "summary": "Rooms and spawn.", "file": "level.zintriq-plugin.json"},
    {"id": "official-data", "name": "Data", "summary": "Tables without raw SQL.", "file": "data.zintriq-plugin.json"},
    {"id": "official-logic", "name": "Logic", "summary": "State machine and workflows.", "file": "logic.zintriq-plugin.json"},
    {"id": "official-text", "name": "Text", "summary": "Line sequence.", "file": "text.zintriq-plugin.json"},
    {"id": "official-vector", "name": "Vector", "summary": "SVG path.", "file": "vector.zintriq-plugin.json"},
    {"id": "official-bitmap", "name": "Bitmap", "summary": "Raster canvas.", "file": "bitmap.zintriq-plugin.json"},
    {"id": "official-model3d", "name": "Model 3D", "summary": "Mesh, LOD, transform.", "file": "model3d.zintriq-plugin.json"},
    {"id": "official-material", "name": "Material", "summary": "PBR-style local preview.", "file": "material.zintriq-plugin.json"},
    {"id": "official-particle", "name": "Particle", "summary": "Emitters.", "file": "particle.zintriq-plugin.json"},
    {"id": "official-terrain", "name": "Terrain", "summary": "Height and noise.", "file": "terrain.zintriq-plugin.json"},
    {"id": "official-video", "name": "Video", "summary": "Clip preview.", "file": "video.zintriq-plugin.json"},
    {"id": "official-font", "name": "Font", "summary": "Glyph preview.", "file": "font.zintriq-plugin.json"},
    {"id": "official-document", "name": "Document", "summary": "Pages and blocks.", "file": "document.zintriq-plugin.json"},
    {"id": "official-spreadsheet", "name": "Spreadsheet", "summary": "Rows, no arbitrary SQL.", "file": "spreadsheet.zintriq-plugin.json"},
    {"id": "official-map", "name": "Map", "summary": "Lat/lng local preview.", "file": "map.zintriq-plugin.json"},
    {"id": "official-circuit", "name": "Circuit", "summary": "Nets, Manhattan route, DRC.", "file": "circuit.zintriq-plugin.json"},
    {"id": "official-chip", "name": "Chip", "summary": "Die route preview.", "file": "chip.zintriq-plugin.json"},
    {"id": "official-quantum", "name": "Quantum", "summary": "Local amplitudes.", "file": "quantum.zintriq-plugin.json"},
    {"id": "official-ai", "name": "AI", "summary": "Local weights complete.", "file": "ai.zintriq-plugin.json"},
    {"id": "official-cad", "name": "CAD", "summary": "B-rep solid.", "file": "cad.zintriq-plugin.json"},
    {"id": "official-physics", "name": "Physics", "summary": "Body step.", "file": "physics.zintriq-plugin.json"},
    {"id": "official-skeleton", "name": "Skeleton", "summary": "CCD IK and LBS.", "file": "skeleton.zintriq-plugin.json"},
    {"id": "official-film", "name": "Film", "summary": "NLE tracks, razor, EDL.", "file": "film.zintriq-plugin.json"},
    {"id": "official-vr", "name": "VR space", "summary": "Local stereo preview.", "file": "vr.zintriq-plugin.json"},
    {"id": "official-robotics", "name": "Robotics", "summary": "Joint program.", "file": "robotics.zintriq-plugin.json"},
    {"id": "official-print3d", "name": "3D print", "summary": "G-code compile.", "file": "print3d.zintriq-plugin.json"},
    {"id": "official-cnc", "name": "CNC", "summary": "Toolpath compile.", "file": "cnc.zintriq-plugin.json"},
    {"id": "official-chain", "name": "Chain ledger", "summary": "Local blocks only.", "file": "chain.zintriq-plugin.json"},
    {"id": "official-meta", "name": "Meta", "summary": "Describe / simulate / instantiate.", "file": "meta.zintriq-plugin.json"},
    {"id": "official-meta-meta", "name": "Meta-meta", "summary": "Unbounded meta_level.", "file": "meta-meta.zintriq-plugin.json"},
)


COMMUNITY = (
    {
        "id": "community-marks",
        "name": "Marks pack",
        "summary": "Approved third-party view marks. Runs sandboxed.",
        "file": "community-marks.zintriq-plugin.json",
        "origin": "third",
        "status": "approved",
        "sandbox": True,
    },
    {
        "id": "community-pending",
        "name": "Pending pack",
        "summary": "Awaiting host review before install.",
        "file": "community-pending.zintriq-plugin.json",
        "origin": "third",
        "status": "pending",
        "sandbox": True,
    },
)

_SANDBOX_BAN = ("eval(", "new Function", "child_process", "XMLHttpRequest", "require(")
_REVIEWS: dict[str, str] = {}
_SUBMITTED: list[dict] = []


class PluginError(ValueError):
    pass


def _decorate(row: dict, origin: str) -> dict:
    out = dict(row)
    out.setdefault("origin", origin)
    out.setdefault("sandbox", origin == "third")
    out.setdefault("form", "view")
    default = "approved" if origin == "official" else str(out.get("status") or "pending")
    out["status"] = _REVIEWS.get(str(out.get("id") or ""), default)
    fname = str(out.get("file") or "")
    if origin == "official" and fname:
        out["download"] = "/plugins/files/" + Path(fname).name
    return out


def load_disk_packs(data_root: Path) -> list[dict]:
    folder = Path(data_root) / "plugins"
    if not folder.is_dir():
        return []
    rows = []
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict) and raw.get("id") and raw.get("name"):
            rows.append(raw)
    return rows


def catalog(*, include_pending: bool = False, remote_path: str | None = None, data_root: Path | str | None = None) -> list[dict]:
    rows = [_decorate(row, "official") for row in PACKS]
    for row in rows:
        fname = str(row.get("file") or "")
        if not fname:
            continue
        full = official_pack_file(fname)
        if full and full.get("sha256"):
            row["sha256"] = full["sha256"]
    extra = [dict(row) for row in COMMUNITY] + [dict(row) for row in _SUBMITTED]
    root = data_root if data_root is not None else (os.environ.get("ZINTRIQ_DATA_DIR") or "").strip()
    if root:
        extra.extend(load_disk_packs(Path(root)))
    seen = {row["id"] for row in rows}
    for row in extra:
        item = _decorate(row, str(row.get("origin") or "third"))
        if item["id"] in seen:
            continue
        if include_pending or item["status"] == "approved":
            rows.append(item)
            seen.add(item["id"])
    path = remote_path if remote_path is not None else (os.environ.get("ZINTRIQ_PLUGIN_CATALOG") or "").strip()
    if path:
        for item in load_remote(path):
            if item["id"] in seen:
                continue
            decorated = _decorate(item, str(item.get("origin") or "third"))
            if include_pending or decorated["status"] == "approved":
                rows.append(decorated)
                seen.add(decorated["id"])
    return rows


def validate_manifest(pack: dict) -> dict:
    if not isinstance(pack, dict):
        raise PluginError("manifest must be an object")
    ident = str(pack.get("id") or "").strip()
    name = str(pack.get("name") or "").strip()
    if not ident or not name:
        raise PluginError("manifest needs id and name")
    form = str(pack.get("form") or "").strip() or "view"
    pack = dict(pack)
    pack["form"] = form[:128]
    pack.setdefault("loop", "plugin-project-plugin")
    blob = json.dumps(pack, ensure_ascii=False)
    third = str(pack.get("origin") or "") == "third" or ident.startswith("community-")
    if third:
        for ban in _SANDBOX_BAN:
            if ban in blob:
                raise PluginError("sandbox rejected " + ban)
    return pack


def review(pack_id: str, status: str) -> dict:
    if status not in {"approved", "rejected", "pending"}:
        raise PluginError("unknown review")
    _REVIEWS[str(pack_id)] = status
    return {"id": pack_id, "status": status}


def submit(pack: dict) -> dict:
    body = dict(pack)
    body["origin"] = "third"
    body.setdefault("status", "pending")
    body["sandbox"] = True
    ident = str(body.get("id") or "").strip()
    body["id"] = ident
    body.setdefault("file", ident + ".zintriq-plugin.json")
    body = validate_manifest(body)
    _SUBMITTED[:] = [row for row in _SUBMITTED if row.get("id") != ident]
    _SUBMITTED.append(body)
    return body


def installable(pack: dict) -> bool:
    return str(pack.get("status") or "") == "approved"


def reset_reviews() -> None:
    _REVIEWS.clear()
    _SUBMITTED.clear()


def plugin_key() -> bytes:
    return (os.environ.get("ZINTRIQ_PLUGIN_KEY") or "zintriq-local-plugin").encode("utf-8")


def _body_bytes(pack: dict) -> bytes:
    body = {key: pack[key] for key in pack if key != "signature"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")


def sign_pack(pack: dict, key: bytes | None = None) -> dict:
    out = dict(pack)
    out.pop("signature", None)
    out["signature"] = hmac.new(key or plugin_key(), _body_bytes(out), hashlib.sha256).hexdigest()
    return out


def verify_pack(pack: dict, key: bytes | None = None, *, required: bool = False) -> bool:
    sig = str(pack.get("signature") or "")
    if not sig:
        if required:
            raise PluginError("unsigned pack")
        return True
    expect = hmac.new(key or plugin_key(), _body_bytes(pack), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        raise PluginError("bad signature")
    return True


def load_remote(path: str) -> list[dict]:
    target = Path(path)
    if not target.is_file():
        raise PluginError("remote catalog missing")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginError("remote catalog is not JSON") from exc
    rows = data.get("packs") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise PluginError("remote catalog needs packs")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        verify_pack(row, required=True)
        validate_manifest(row)
        out.append(dict(row))
    return out


def catalog_digest(doc: dict) -> str:
    body = {key: value for key, value in doc.items() if key != "digest"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def hosted_catalog() -> dict:
    packs = []
    for row in catalog(include_pending=True):
        signed = sign_pack(dict(row))
        body = {key: signed[key] for key in signed if key != "signature"}
        digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        signed["category"] = "official" if str(signed.get("origin") or "official") == "official" else "community"
        signed["channel"] = "stable" if signed.get("status") == "approved" else "review"
        signed["compat"] = "desktop"
        signed["sha256"] = digest
        packs.append(signed)
    doc = {"channel": "stable", "channels": ["stable", "review"], "host": "127.0.0.1", "kind": "store", "mirror": True, "packs": packs, "protocol": 7, "revoked": [], "signed": True, "version": 7}
    doc["digest"] = catalog_digest(doc)
    doc["etag"] = doc["digest"][:16]
    return doc


def mirror_root(data_root: Path) -> Path:
    folder = Path(data_root) / "store"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def mirror_catalog(data_root: Path, doc: dict | None = None) -> Path:
    payload = doc if isinstance(doc, dict) else hosted_catalog()
    path = mirror_root(data_root) / "catalog.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_mirror(data_root: Path) -> dict:
    path = mirror_root(data_root) / "catalog.json"
    if not path.is_file():
        mirror_catalog(data_root)
    return json.loads(path.read_text(encoding="utf-8"))


def write_installed(data_root: Path, rows: list[str]) -> list[str]:
    path = mirror_root(data_root) / "installed.json"
    cleaned = []
    seen: set[str] = set()
    for item in rows:
        ident = str(item or "")
        if not ident or ident in seen:
            continue
        seen.add(ident)
        cleaned.append(ident)
    path.write_text(json.dumps(cleaned, ensure_ascii=False), encoding="utf-8")
    return cleaned


def record_install(data_root: Path, pack_id: str) -> list[str]:
    rows = installed_index(data_root)
    ident = str(pack_id or "")
    if ident and ident not in rows:
        rows.append(ident)
    return write_installed(data_root, rows)


def installed_index(data_root: Path) -> list[str]:
    path = mirror_root(data_root) / "installed.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(item) for item in raw] if isinstance(raw, list) else []


def pack_view_id(pack: dict | None) -> str:
    if not isinstance(pack, dict):
        return ""
    explicit = str(pack.get("view") or "").strip()
    if explicit:
        return explicit
    mapped = view_id_from_form(str(pack.get("form") or ""), str(pack.get("kindValue") or ""))
    if mapped:
        return mapped
    ident = str(pack.get("id") or "")
    if ident.startswith("official-"):
        tail = ident[9:]
        if tail in OFFICIAL_VIEW_IDS:
            return tail
    return ""


def desc_fingerprint(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def uninstall_plugin(data_root: Path, pack_id: str, *, delete: bool = False, delete_draft: bool = False) -> dict:
    ident = str(pack_id or "").strip()
    if not ident:
        raise PluginError("pack id missing")
    root = Path(data_root)
    mapped = plugin_drafts(root).get(ident) or ""
    pack = next((row for row in catalog(include_pending=True, data_root=root) if row["id"] == ident), None)
    rows = [item for item in installed_index(root) if item != ident]
    view = pack_view_id(pack)
    if not view and ident.startswith("official-"):
        tail = ident[9:]
        if tail in OFFICIAL_VIEW_IDS:
            view = tail
    kept = {row["id"]: row for row in catalog(include_pending=True, data_root=root) if row["id"] in set(rows)}
    needed = {pack_view_id(item) for item in kept.values() if pack_view_id(item)}
    if view and view not in needed:
        drop = {view, "official-" + view} - set(kept)
        rows = [item for item in rows if item not in drop]
    write_installed(root, rows)
    deleted = False
    binding_cleared = ""
    if delete:
        _SUBMITTED[:] = [row for row in _SUBMITTED if str(row.get("id") or "") != ident]
        _REVIEWS.pop(ident, None)
        # Remove clears the on-disk plugins/ copy (official + stamp); Disable only drops the install index.
        folder = (root / "plugins").resolve()
        name = Path(str((pack or {}).get("file") or (ident + ".zintriq-plugin.json"))).name
        path = (folder / name).resolve()
        if path.is_file() and path.parent == folder:
            path.unlink()
            deleted = True
        elif pack and pack.get("stamp") and not path.is_file():
            deleted = True
        # Always drop Use binding on Remove so reinstall does not show a ghost draft_slug.
        if mapped:
            forget_plugin_draft(root, ident)
            binding_cleared = mapped
        elif delete_draft:
            forget_plugin_draft(root, ident)
    return {
        "binding_cleared": binding_cleared,
        "cleared": deleted,
        "deleted": deleted,
        "disabled": True,
        "draft_slug": mapped,
        "id": ident,
        "installed": rows,
        "view": view,
    }


def plugin_drafts(data_root: Path) -> dict[str, str]:
    path = mirror_root(data_root) / "plugin-drafts.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if str(key) and str(value)}


def pack_sha256(pack: dict) -> str:
    body = {key: value for key, value in (pack or {}).items() if key != "sha256"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def verify_pack_digest(pack: dict, *, required: bool = False) -> bool:
    """Same fingerprint as portal `/plugins/files` downloads and desktop Open/install."""
    expect = str((pack or {}).get("sha256") or "").strip().lower()
    if not expect:
        if required:
            raise PluginError("missing sha256")
        return True
    if pack_sha256(pack).lower() != expect:
        raise PluginError("sha256 mismatch")
    return True


def looks_like_plugin_pack(pack: dict) -> bool:
    if not isinstance(pack, dict):
        return False
    ident = str(pack.get("id") or "").strip()
    fname = str(pack.get("file") or "")
    if ident.startswith("official-") or ident.startswith("community-"):
        return True
    if fname.endswith(".zintriq-plugin.json"):
        return True
    if pack.get("stamp") or pack.get("signature"):
        return True
    if pack.get("origin") in {"official", "third", "remote", "account"}:
        return True
    if ident and pack.get("view") and pack.get("form"):
        return True
    return False


def pack_document_code(pack: dict) -> str:
    """Single-plugin New skeleton — never mash multiple packs into one system."""
    document = pack.get("document")
    if document is None:
        extra = official_pack_file(str(pack.get("file") or ""))
        document = (extra or {}).get("document")
    if document is None:
        from meta.description import to_json
        from meta.instantiation.errors import InstantiationError
        from meta.instantiation.system import child_for_part_kind

        try:
            desc = child_for_part_kind(part_kind_from_pack(pack), title=str(pack.get("name") or "Part"))
            document = json.loads(to_json(desc))
        except (InstantiationError, TypeError, ValueError, json.JSONDecodeError):
            return "{}"
    if isinstance(document, dict):
        return json.dumps(document, ensure_ascii=False, indent=2)
    if isinstance(document, str) and document.strip():
        return document
    return "{}"


def stamp_timeline(data_root: Path | str | None, slug: str = "") -> list[dict]:
    if data_root is None:
        return []
    path = Path(data_root) / "stamp-timeline.json"
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(rows, list):
        return []
    wanted = str(slug or "").strip()
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        if wanted and str(item.get("slug") or "") != wanted:
            continue
        out.append(
            {
                "at": int(item.get("at") or 0),
                "fingerprint": str(item.get("fingerprint") or "")[:64],
                "pack_id": str(item.get("pack_id") or "")[:80],
                "slug": str(item.get("slug") or "")[:80],
                "document": str(item.get("document") or "")[:80000],
            }
        )
    return out[-24:]


def record_stamp_timeline(
    data_root: Path | str | None,
    *,
    slug: str,
    fingerprint: str,
    pack_id: str = "",
    document: dict | str | None = None,
) -> list[dict]:
    if data_root is None:
        return []
    dest = str(slug or "").strip()
    fp = str(fingerprint or "").strip()
    if not dest or not fp:
        return stamp_timeline(data_root, dest)
    path = Path(data_root) / "stamp-timeline.json"
    rows: list[dict] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = []
        if isinstance(raw, list):
            rows = [item for item in raw if isinstance(item, dict)]
    if isinstance(document, dict):
        blob = json.dumps(document, ensure_ascii=False)
    else:
        blob = str(document or "")
    rows.append(
        {
            "at": int(__import__("time").time()),
            "fingerprint": fp[:64],
            "pack_id": str(pack_id or "")[:80],
            "slug": dest[:80],
            "document": blob[:80000],
        }
    )
    path.write_text(json.dumps(_cap_stamp_timeline(rows), ensure_ascii=False, indent=2), encoding="utf-8")
    return [item for item in stamp_timeline(data_root, dest)]


def _cap_stamp_timeline(rows: list[dict]) -> list[dict]:
    other: list[dict] = []
    by_slug: dict[str, list[dict]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "")
        if not slug:
            other.append(item)
            continue
        by_slug.setdefault(slug, []).append(item)
    out = list(other)
    for slug, items in by_slug.items():
        seen: set[str] = set()
        kept: list[dict] = []
        for item in reversed(items):
            fp = str(item.get("fingerprint") or "")
            if not fp or fp in seen:
                continue
            seen.add(fp)
            kept.append(item)
            if len(kept) >= 24:
                break
        kept.reverse()
        out.extend(kept)
    return out


def restore_stamp_document(data_root: Path | str | None, *, slug: str, fingerprint: str) -> dict:
    dest = str(slug or "").strip()
    wanted = str(fingerprint or "").strip()
    if not dest or not wanted:
        raise PluginError("timeline restore needs slug and fingerprint")
    rows = list(reversed(stamp_timeline(data_root, dest)))
    match = next((item for item in rows if str(item.get("fingerprint") or "") == wanted and item.get("document")), None)
    if not match:
        raise PluginError("no stored document for that fingerprint")
    from desktop.meta_store import save_draft

    save_draft(dest, code=str(match["document"]), current=True, base=Path(data_root) if data_root else None)
    return {"fingerprint": wanted, "restored": True, "slug": dest}


def remember_plugin_draft(data_root: Path, pack_id: str, slug: str) -> dict[str, str]:
    rows = plugin_drafts(data_root)
    ident = str(pack_id or "").strip()
    dest = str(slug or "").strip()
    if ident and dest:
        rows[ident] = dest
    path = mirror_root(data_root) / "plugin-drafts.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def forget_plugin_draft(data_root: Path, pack_id: str) -> dict[str, str]:
    rows = plugin_drafts(data_root)
    ident = str(pack_id or "").strip()
    rows.pop(ident, None)
    path = mirror_root(data_root) / "plugin-drafts.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def catalog_delta(old: dict | None, new: dict | None = None) -> dict:
    left = old if isinstance(old, dict) else {}
    right = new if isinstance(new, dict) else hosted_catalog()
    old_map = {str(row.get("id")): str(row.get("sha256") or "") for row in left.get("packs") or [] if isinstance(row, dict)}
    new_map = {str(row.get("id")): str(row.get("sha256") or "") for row in right.get("packs") or [] if isinstance(row, dict)}
    added = [ident for ident in new_map if ident not in old_map]
    removed = [ident for ident in old_map if ident not in new_map]
    updated = [ident for ident in new_map if ident in old_map and old_map[ident] != new_map[ident]]
    return {"added": added, "etag": str(right.get("etag") or ""), "protocol": 7, "removed": removed, "revoked": list(right.get("revoked") or []), "updated": updated}


def queue_pack(data_root: Path, pack_id: str) -> list[str]:
    path = mirror_root(data_root) / "queue.json"
    rows: list[str] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                rows = [str(item) for item in raw]
        except (OSError, json.JSONDecodeError):
            rows = []
    ident = str(pack_id or "")
    if ident and ident not in rows:
        rows.append(ident)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def signed_index(data_root: Path) -> dict:
    doc = load_mirror(data_root)
    path = mirror_root(data_root) / "index.sha256"
    digest = catalog_digest(doc)
    path.write_text(digest, encoding="utf-8")
    return {"digest": digest, "path": str(path), "protocol": 7}


def revoke_pack(data_root: Path, pack_id: str) -> list[str]:
    path = mirror_root(data_root) / "revoked.json"
    rows: list[str] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                rows = [str(item) for item in raw]
        except (OSError, json.JSONDecodeError):
            rows = []
    ident = str(pack_id or "")
    if ident and ident not in rows:
        rows.append(ident)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def fetch_store(url: str) -> list[dict]:
    raw = str(url or "").strip()
    if not raw:
        raise PluginError("store url missing")
    if raw.startswith("file:"):
        return load_remote(raw.replace("file://", ""))
    if Path(raw).is_file():
        return load_remote(raw)
    if not (raw.startswith("http://127.0.0.1") or raw.startswith("https://127.0.0.1")):
        raise PluginError("store host not allowed")
    from urllib.request import urlopen

    try:
        with urlopen(raw, timeout=3) as handle:  # noqa: S310
            data = json.loads(handle.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise PluginError("store fetch failed") from exc
    rows = data.get("packs") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise PluginError("store needs packs")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        verify_pack(row, required=True)
        validate_manifest(row)
        out.append(dict(row))
    return out


OFFICIAL_VIEW_IDS = frozenset(str(row["id"])[9:] for row in PACKS if str(row.get("id") or "").startswith("official-"))


def view_id_from_form(form: str = "", kind: str = "") -> str:
    raw = str(kind or form or "").strip().lower().replace("_", "-")
    aliases = {
        "app": "ui",
        "iot": "circuit",
        "os": "meta",
        "page": "",
        "view": "",
        "web": "ui",
        "webpage": "ui",
        "website": "ui",
    }
    mapped = aliases.get(raw, raw.split(".", 1)[0])
    if mapped in OFFICIAL_VIEW_IDS:
        return mapped
    return ""


def normalize_form(value: str) -> str:
    text = str(value or "").strip()
    return text[:128] if text else "view"


def part_kind_from_pack(pack: dict) -> str:
    explicit = str(pack.get("kindValue") or pack.get("kind") or pack.get("part_kind") or "").strip()
    if explicit:
        return explicit
    ident = str(pack.get("id") or "")
    slug = ident[9:] if ident.startswith("official-") else ident
    from_form = view_id_from_form(str(pack.get("form") or ""), "")
    if from_form:
        return from_form
    aliases = {
        "cad": "cad.solid",
        "channel": "social.channel",
        "checkout": "commerce.checkout",
        "data": "data.table",
        "federate": "social.federate",
        "film": "film.cut",
        "meta": "os",
        "meta-meta": "os",
        "node": "node.graph",
        "physics": "physics.body",
        "settle": "commerce.settle",
        "skeleton": "skeleton.rig",
        "ui": "page",
        "weights": "llm.weights",
    }
    return aliases.get(slug, slug or "scene")


def stamp_id(name: str, data_root: Path | str | None = None) -> str:
    ident, _existing = stamp_target(name, data_root=data_root)
    return ident


def stamp_target(name: str, data_root: Path | str | None = None) -> tuple[str, dict | None]:
    label = str(name or "").strip()[:80]
    base = plugin_key_slug({"id": label or "plugin", "name": label or "plugin"})
    ident = "community-" + base
    rows = catalog(include_pending=True, data_root=data_root)
    by_id = next((row for row in rows if row["id"] == ident), None)
    if by_id and by_id.get("stamp"):
        return ident, by_id
    named = next((row for row in rows if row.get("stamp") and str(row.get("name") or "") == label), None)
    if named:
        return str(named["id"]), named
    if by_id is None:
        return ident, None
    seen = {row["id"] for row in rows}
    n = 2
    while f"{ident}-{n}" in seen:
        n += 1
    return f"{ident}-{n}", None


def stamp_plugin(
    *,
    name: str,
    form: str = "",
    summary: str = "",
    kind: str = "",
    document: dict | str | None = None,
    data_root: Path | None = None,
    pack_id: str = "",
    draft_slug: str = "",
) -> dict:
    label = str(name or "").strip()[:80]
    if not label:
        raise PluginError("plugin needs a name")
    wanted_form = normalize_form(form)
    view = view_id_from_form(wanted_form, kind)
    ident = ""
    existing = None
    explicit = str(pack_id or "").strip()
    if explicit and data_root is not None:
        rows = catalog(include_pending=True, data_root=data_root)
        hit = next((row for row in rows if row["id"] == explicit and row.get("stamp")), None)
        if hit:
            ident, existing = explicit, hit
    if not ident and draft_slug and data_root is not None:
        bound = plugin_drafts(Path(data_root))
        for key, slug in bound.items():
            if slug != draft_slug:
                continue
            rows = catalog(include_pending=True, data_root=data_root)
            hit = next((row for row in rows if row["id"] == key and row.get("stamp")), None)
            if hit:
                ident, existing = str(hit["id"]), hit
                break
    if not ident:
        ident, existing = stamp_target(label, data_root=data_root)
    replaced = existing is not None
    pack = {
        "code": False,
        "file": "",
        "form": wanted_form,
        "id": ident,
        "kindValue": str(kind or view).strip()[:128],
        "name": label,
        "origin": "third",
        "stamp": True,
        "summary": str(summary or wanted_form).strip()[:200] or wanted_form,
        "view": view,
    }
    if document is None and replaced and existing.get("document") is not None:
        pack["document"] = existing["document"]
    elif document is not None:
        if isinstance(document, str) and document.strip():
            try:
                parsed = json.loads(document)
            except json.JSONDecodeError as exc:
                raise PluginError("plugin document must be JSON") from exc
            pack["document"] = parsed
        elif isinstance(document, dict):
            pack["document"] = document
    pack["file"] = pack["id"] + ".zintriq-plugin.json"
    cycle = loop_cycle(pack, approved=True)
    stored = cycle["pack"]
    if data_root is not None:
        folder = Path(data_root) / "plugins"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / stored["file"]
        path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        record_install(Path(data_root), stored["id"])
        cycle["path"] = str(path)
        cycle["pane"] = view or "code"
        bound = plugin_drafts(Path(data_root)).get(stored["id"]) or stored["id"]
        record_stamp_timeline(
            data_root,
            slug=str(bound),
            fingerprint=desc_fingerprint(stored.get("document")),
            pack_id=str(stored.get("id") or ""),
            document=stored.get("document"),
        )
    cycle["replaced"] = replaced
    return cycle


def unlocked_installs(data_root: Path | str | None) -> list[str]:
    if data_root is None:
        return []
    root = Path(data_root)
    rows = list(installed_index(root))
    have = set(rows)
    for pack in catalog(include_pending=True, data_root=root):
        if pack.get("id") not in have:
            continue
        view = pack_view_id(pack)
        if view:
            rows.append(view)
            rows.append("official-" + view)
    return rows


HW_PACK_IDS = frozenset({"official-robotics", "official-print3d", "official-cnc", "robotics", "print3d", "cnc"})


def hardware_host_unlocked(installed: list[str] | tuple[str, ...] | set[str]) -> bool:
    have = {str(item) for item in installed}
    return bool(have & HW_PACK_IDS)


def view_unlocked(view_id: str, installed: list[str] | tuple[str, ...] | set[str]) -> bool:
    from meta.editor_views import CORE_VIEW_IDS

    ident = str(view_id or "").strip()
    have = {str(item) for item in installed}
    if ident in CORE_VIEW_IDS:
        return "meta" in have or "official-meta" in have or ident in have or f"official-{ident}" in have
    if ident in have or f"official-{ident}" in have:
        return True
    for item in have:
        mapped = view_id_from_form(item, item)
        if mapped == ident:
            return True
    return False


def plugin_key_slug(pack: dict) -> str:
    ident = str(pack.get("id") or "plugin")
    slug = ident[9:] if ident.startswith("official-") else ident
    slug = slug.replace("_", "-")
    cleaned = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in slug.lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return (cleaned or "plugin")[:64]


def project_from_packs(packs: list[dict], *, title: str = "plugin-project"):
    from meta.instantiation.errors import InstantiationError
    from meta.instantiation.system import child_for_part_kind, software_system
    from meta.runtime.structure_systems import tag_system

    parts = []
    seen: set[str] = set()
    for pack in packs:
        if not isinstance(pack, dict):
            continue
        key = plugin_key_slug(pack)
        if key in seen:
            continue
        seen.add(key)
        kind = part_kind_from_pack(pack)
        name = str(pack.get("name") or key)
        document = pack.get("document")
        child = None
        if document is not None:
            from meta.description import from_json

            try:
                raw = document if isinstance(document, str) else json.dumps(document)
                child = from_json(raw)
            except (TypeError, ValueError):
                child = None
        if child is None:
            try:
                child = child_for_part_kind(kind, title=name)
            except InstantiationError:
                child = child_for_part_kind("scene", title=name)
        parts.append((key, name, child))
    if not parts:
        raise PluginError("project needs at least one pack")
    form = normalize_form((packs[0] or {}).get("form") if packs else "view")
    return tag_system(software_system(title=title, parts=parts), form=form)


_OFFICIAL_FILES: dict[str, dict] = {}


def official_pack_file(filename: str) -> dict | None:
    name = Path(str(filename or "")).name
    if not name.endswith(".json") or ".." in name:
        return None
    cached = _OFFICIAL_FILES.get(name)
    if cached:
        return dict(cached)
    row = next((item for item in PACKS if str(item.get("file") or "") == name), None)
    if not row:
        return None
    pack = _decorate(dict(row), "official")
    ident = str(pack.get("id") or "")
    pack["view"] = ident[9:] if ident.startswith("official-") else ident
    pack["kindValue"] = part_kind_from_pack(pack)
    try:
        from meta.description import to_json
        from meta.instantiation.errors import InstantiationError
        from meta.instantiation.system import child_for_part_kind

        desc = child_for_part_kind(str(pack["kindValue"]), title=str(pack.get("name") or pack["view"]))
        pack["document"] = json.loads(to_json(desc))
    except (InstantiationError, TypeError, ValueError, json.JSONDecodeError):
        pack["document"] = {
            "form": "struct",
            "fields": {
                "kind": {"form": "atom", "type": "string", "value": pack["view"]},
                "title": {"form": "atom", "type": "string", "value": pack.get("name") or pack["view"]},
            },
        }
    pack["stamp"] = False
    pack["js"] = False
    pack["sha256"] = pack_sha256(pack)
    _OFFICIAL_FILES[name] = pack
    return dict(pack)


def primary_installed_pack(data_root: Path | str | None) -> dict | None:
    """First installed editor pack in EDITOR_PLUGINS order (Scene before UI, …)."""
    if data_root is None:
        return None
    root = Path(data_root)
    have = set(installed_index(root))
    if not have:
        return None
    rows = [row for row in catalog(include_pending=False, data_root=root) if row.get("id") in have]
    if not rows:
        return None
    from meta.editor_views import plugin_ids

    order = {vid: index for index, vid in enumerate(plugin_ids())}
    rows.sort(key=lambda row: (order.get(pack_view_id(row) or "", 999), str(row.get("id") or "")))
    return dict(rows[0])


def default_new_code(data_root: Path | str | None) -> str:
    """One primary view skeleton when several plugins are installed (Scene before UI, etc.)."""
    pick = primary_installed_pack(data_root)
    if not pick:
        return "{}"
    return pack_document_code(pick)


def record_plugin_rebind(data_root: Path, pack_id: str, old_slug: str, new_slug: str) -> list[dict]:
    """Append old→new draft binding for status-bar timeline."""
    path = mirror_root(data_root) / "rebind-timeline.json"
    rows: list[dict] = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                rows = [row for row in data if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            rows = []
    rows.append(
        {
            "at": int(datetime.now(timezone.utc).timestamp()),
            "from": str(old_slug or ""),
            "id": str(pack_id or ""),
            "to": str(new_slug or ""),
        }
    )
    rows = rows[-24:]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def rebind_timeline(data_root: Path) -> list[dict]:
    path = mirror_root(data_root) / "rebind-timeline.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [row for row in data if isinstance(row, dict)][-24:] if isinstance(data, list) else []


def unlocked_editor_views(surface: str, data_root: Path | str | None) -> list[dict]:
    from meta.editor_views import list_views as list_editor_views

    rows = list_editor_views(surface)
    if data_root is None:
        return []
    installed = unlocked_installs(data_root)
    return [item for item in rows if view_unlocked(item["id"], installed)]


def loop_cycle(manifest: dict, *, approved: bool = False) -> dict:
    """plugin → catalog → (optional approve) → project part. Local only."""
    pack = submit(manifest)
    if approved:
        review(pack["id"], "approved")
        pack = dict(pack)
        pack["status"] = "approved"
    has_project = pack.get("status") == "approved"
    if has_project:
        project_from_packs([pack], title=str(pack.get("name") or pack["id"]))
    return {
        "cdn": False,
        "form": pack.get("form") or "view",
        "loop": "plugin-project-plugin",
        "pack": pack,
        "project": has_project,
        "status": pack.get("status"),
        "unity": False,
        "wan": False,
    }
