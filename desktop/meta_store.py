"""Local meta-instantiation and draft store. Lives under ZINTRIQ_DATA_DIR, not the cloud."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from flask import Response

from desktop.layout import normalize_layout
from desktop.search_text import lookup, tokens as _tokens
from desktop.server_mode import desktop_enabled
from meta.instantiation import Artifact, InstantiationError, TARGET_DESKTOP_HOST, TARGET_WEB_BUILD, validate_asset_name, validate_slug
from meta.instantiation.artifact import KNOWN_TARGETS

ARTIFACTS_DIRNAME = "artifacts"
DRAFTS_DIRNAME = "drafts"
SITES_DIRNAME = "sites"
ASSETS_DIRNAME = "assets"
CURRENT_POINTER = "_current.json"
_ASSET_MAX = 256 * 1024
_ASSET_MAX_COUNT = 24
_ASSET_MIME = {
    "gif": "image/gif",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class MetaStoreError(ValueError):
    """Local artifact or draft store cannot read or write."""


def data_dir() -> Path:
    raw = (os.environ.get("ZINTRIQ_DATA_DIR") or "").strip()
    if not raw:
        raise MetaStoreError("ZINTRIQ_DATA_DIR is required")
    return Path(raw)


def artifacts_root(base: Path | None = None) -> Path:
    return (base or data_dir()) / ARTIFACTS_DIRNAME


def drafts_root(base: Path | None = None) -> Path:
    return (base or data_dir()) / DRAFTS_DIRNAME


def sites_root(base: Path | None = None) -> Path:
    return (base or data_dir()) / SITES_DIRNAME


def assets_root(base: Path | None = None) -> Path:
    return (base or data_dir()) / ASSETS_DIRNAME


def artifact_path(slug: str, base: Path | None = None) -> Path:
    return artifacts_root(base) / f"{validate_slug(slug)}.json"


def draft_path(slug: str, base: Path | None = None) -> Path:
    return drafts_root(base) / f"{validate_slug(slug)}.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            fd = -1
    finally:
        if fd >= 0:
            os.close(fd)
    os.replace(tmp, path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            fd = -1
    finally:
        if fd >= 0:
            os.close(fd)
    os.replace(tmp, path)


def save_artifact(artifact: Artifact, *, base: Path | None = None) -> Path:
    if artifact.target not in KNOWN_TARGETS or not artifact.slug:
        raise MetaStoreError("artifacts need a known target and a slug")
    path = artifact_path(artifact.slug, base)
    _atomic_write(path, json.dumps(artifact.to_data(), ensure_ascii=False, sort_keys=True))
    if artifact.target == TARGET_WEB_BUILD:
        save_site_files(artifact, base=base)
    else:
        leftover = sites_root(base) / validate_slug(artifact.slug)
        if leftover.exists():
            shutil.rmtree(leftover)
    index_upsert(
        "artifact",
        artifact.slug,
        str(artifact.checksum or "") + " " + str(artifact.target or "") + " " + str(artifact.payload or "")[:40000],
        target=str(artifact.target or ""),
        base=base,
    )
    return path


def load_artifact(slug: str, *, base: Path | None = None) -> Artifact:
    path = artifact_path(slug, base)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MetaStoreError(f"no artifact for slug {slug!r}") from exc
    except OSError as exc:
        raise MetaStoreError("cannot read artifact") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MetaStoreError("artifact file is not JSON") from exc
    try:
        return Artifact.from_data(data)
    except InstantiationError as exc:
        raise MetaStoreError(str(exc)) from exc


def save_site_files(artifact: Artifact, *, base: Path | None = None) -> Path:
    """Write relative-link HTML next to the artifact. Not a Flask route."""
    from meta.instantiation.page import rendered_site_files

    if artifact.target != TARGET_WEB_BUILD or not artifact.slug:
        raise MetaStoreError("only web_build artifacts with a slug can be exported")
    slug = validate_slug(artifact.slug)
    root = sites_root(base) / slug
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for name, text in rendered_site_files(artifact):
        if name != "index.html":
            validate_slug(Path(name).stem)
        _atomic_write(root / name, text)
    _atomic_write(root / "meta.json", json.dumps(site_meta_dict(artifact), ensure_ascii=False, sort_keys=True))
    _copy_assets_into_site(slug, root, base=base)
    return root


def site_meta_dict(artifact: Artifact) -> dict:
    from meta.description import to_json
    from meta.instantiation import description_from_artifact

    return {
        "description": json.loads(to_json(description_from_artifact(artifact))),
        "slug": artifact.slug,
        "target": artifact.target,
    }


def list_site_files(slug: str, *, base: Path | None = None) -> list[str]:
    root = sites_root(base) / validate_slug(slug)
    if not root.is_dir():
        return []
    names = []
    for path in sorted(root.glob("*.html")):
        if not path.is_file() or path.parent != root:
            continue
        if path.name != "index.html":
            try:
                validate_slug(path.stem)
            except InstantiationError:
                continue
        names.append(path.name)
    for name in list_assets(slug, base=base):
        if name not in names:
            names.append(name)
    return names


def zip_site(slug: str, *, base: Path | None = None) -> bytes:
    """Zip exported HTML for one slug. Paths are slug/file.html only."""
    import io
    import zipfile

    clean = validate_slug(slug)
    names = list_site_files(clean, base=base)
    if not names:
        raise MetaStoreError(f"no exported site for slug {clean!r}")
    root = sites_root(base) / clean
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            payload = _site_member_bytes(root, name, slug=clean, base=base)
            archive.writestr(f"{clean}/{name}", payload)
        meta_path = root / "meta.json"
        if meta_path.is_file():
            meta_text = meta_path.read_text(encoding="utf-8")
        else:
            meta_text = json.dumps(site_meta_dict(load_artifact(clean, base=base)), ensure_ascii=False, sort_keys=True)
        archive.writestr(f"{clean}/meta.json", meta_text)
    return buf.getvalue()


def zip_app(slug: str, *, base: Path | None = None) -> bytes:
    """Zip a local desktop_host recipe. Not a store installer."""
    import io
    import zipfile

    clean = validate_slug(slug)
    folder = (base or data_dir()) / "desktop" / clean
    if not folder.is_dir():
        raise MetaStoreError(f"no app pack for slug {clean!r}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(folder)
            archive.writestr(f"{clean}/{rel.as_posix()}", path.read_bytes())
    return buf.getvalue()


_MAX_SITE_ZIP = 4 * 1024 * 1024
_MAX_SITE_ZIP_FILES = 48
_MAX_SITE_ZIP_MEMBER = 512 * 1024


def import_site_zip(data: bytes, *, slug: str | None = None, base: Path | None = None) -> dict:
    """Restore a site from a zip that contains slug/meta.json. HTML is re-rendered."""
    import io
    import zipfile

    from meta.description import from_json, to_json
    from meta.instantiation import TARGET_WEB_BUILD, description_from_artifact, instantiate

    raw = bytes(data or b"")
    if not raw or len(raw) > _MAX_SITE_ZIP:
        raise MetaStoreError("site zip is missing or too large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise MetaStoreError("not a zip file") from exc
    infos = archive.infolist()
    if len(infos) > _MAX_SITE_ZIP_FILES:
        raise MetaStoreError("site zip has too many files")
    meta_text = None
    images: list[tuple[str, bytes]] = []
    for info in infos:
        if info.file_size > _MAX_SITE_ZIP_MEMBER:
            raise MetaStoreError("site zip member too large")
        mapped = _zip_member_parts(info.filename)
        if mapped is None:
            raise MetaStoreError("site zip has an unsafe path")
        _member_slug, name = mapped
        if name == "meta.json":
            meta_text = archive.read(info).decode("utf-8")
        else:
            try:
                asset_name = validate_asset_name(name)
            except InstantiationError:
                asset_name = ""
            if asset_name:
                images.append((asset_name, archive.read(info)))
    if not meta_text:
        raise MetaStoreError("site zip is missing meta.json")
    try:
        meta = json.loads(meta_text)
    except json.JSONDecodeError as exc:
        raise MetaStoreError("meta.json is not JSON") from exc
    if not isinstance(meta, dict) or "description" not in meta:
        raise MetaStoreError("meta.json is missing description")
    wanted = str(slug or meta.get("slug") or "").strip()
    desc = from_json(json.dumps(meta.get("description")))
    target = str(meta.get("target") or "").strip() or None
    artifact = instantiate(desc, target=target, slug=wanted)
    save_artifact(artifact, base=base)
    for name, blob in images:
        save_asset(artifact.slug, name, blob, base=base)
    save_draft(artifact.slug, code=to_json(description_from_artifact(artifact), indent=2), base=base)
    out = {
        "public_url": artifact.public_url,
        "slug": artifact.slug,
        "code": to_json(description_from_artifact(artifact), indent=2),
        "target": artifact.target,
    }
    if artifact.target == TARGET_WEB_BUILD:
        out["zip_url"] = f"/api/builder-core/meta/sites/{artifact.slug}/zip"
        out["studio"] = f"/studio/meta/{artifact.slug}"
    return out


def import_export_zip(data: bytes, *, slug: str | None = None, base: Path | None = None) -> dict:
    """Open a webpage zip, local .zintriq-app.zip, or a stamp JSON. Store installers are not accepted."""
    import io
    import zipfile

    raw = bytes(data or b"")
    if not raw or len(raw) > _MAX_SITE_ZIP:
        raise MetaStoreError("zip is missing or too large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return import_stamp_bytes(raw, slug=slug, base=base)
    if _zip_has_named_file(archive, "host.json"):
        out = import_app_zip(raw, slug=slug, base=base)
    else:
        out = import_site_zip(raw, slug=slug, base=base)
    record_last_open(out.get("slug") or "", kind="zip", text=str(out.get("code") or "")[:4000], base=base)
    return out


def import_stamp_bytes(data: bytes, *, slug: str | None = None, base: Path | None = None) -> dict:
    from plugin_catalog import PluginError, looks_like_plugin_pack, stamp_plugin, verify_pack_digest

    raw = bytes(data or b"")
    try:
        pack = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetaStoreError("not a zip or stamp JSON") from exc
    if not isinstance(pack, dict):
        raise MetaStoreError("stamp JSON needs an object")
    root = base or data_dir()
    # Site Desc JSON (form/fields, no pack id) → Open as draft, not install.
    if (pack.get("form") or pack.get("fields")) and not looks_like_plugin_pack(pack):
        dest = str(slug or current_draft_slug(base=root) or unused_slug(base=root))
        code = json.dumps(pack, ensure_ascii=False, indent=2)
        save_draft(dest, code=code, current=True, base=root)
        record_last_open(dest, kind="desc", text=code[:4000], base=root)
        return {
            "code": code,
            "installer": False,
            "kind": "desc",
            "slug": dest,
            "store": False,
            "studio": f"/studio/meta/{dest}",
        }
    if not (pack.get("id") or pack.get("name")):
        raise MetaStoreError("stamp JSON needs id or name")
    if pack.get("installer") or pack.get("store") or pack.get("binary"):
        raise MetaStoreError("store installers are not accepted")
    try:
        verify_pack_digest(pack)
    except PluginError as exc:
        raise MetaStoreError(str(exc)) from exc
    try:
        cycle = stamp_plugin(
            name=str(pack.get("name") or pack.get("id") or "plugin"),
            form=str(pack.get("form") or ""),
            summary=str(pack.get("summary") or ""),
            kind=str(pack.get("kindValue") or pack.get("kind") or ""),
            document=pack.get("document") if pack.get("document") is not None else pack.get("code"),
            data_root=root,
        )
    except PluginError as exc:
        raise MetaStoreError(str(exc)) from exc
    stored = cycle.get("pack") or {}
    dest = str(slug or current_draft_slug(base=root) or stored.get("id") or "plugin")
    from plugin_catalog import remember_plugin_draft

    remember_plugin_draft(root, str(stored.get("id") or ""), dest)
    from plugin_catalog import record_install

    if stored.get("id"):
        record_install(root, str(stored.get("id")))
    if stored.get("document") is not None:
        save_draft(dest, code=json.dumps(stored.get("document"), ensure_ascii=False, indent=2), current=True, base=root)
    record_last_open(dest, kind="plugin", text=json.dumps(stored, ensure_ascii=False)[:4000], base=root)
    out = {
        "code": json.dumps(stored.get("document"), ensure_ascii=False, indent=2) if stored.get("document") is not None else "",
        "installer": False,
        "pack": stored,
        "slug": dest,
        "store": False,
        "studio": f"/studio/meta/{dest}",
        "binary": False,
    }
    return out


def record_last_open(slug: str, *, kind: str = "zip", text: str = "", base: Path | None = None) -> None:
    root = base or data_dir()
    path = mirror_search_open(root)
    rows: list[dict] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                rows = [row for row in raw if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            rows = []
    ident = str(slug or "").strip()
    if ident:
        rows = [row for row in rows if str(row.get("slug") or "") != ident]
        rows.insert(0, {"kind": str(kind or "zip"), "slug": ident, "text": str(text or "")[:8000]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows[:40], ensure_ascii=False), encoding="utf-8")


def mirror_search_open(root: Path) -> Path:
    folder = root / "store"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "last-open.json"


def import_app_zip(data: bytes, *, slug: str | None = None, base: Path | None = None) -> dict:
    """Restore a desktop_host recipe into a draft and re-apply the local pack."""
    import io
    import zipfile

    from meta.description import from_json, to_json
    from meta.instantiation import instantiate
    from meta.runtime.desktop_host import apply_desktop_host

    raw = bytes(data or b"")
    if not raw or len(raw) > _MAX_SITE_ZIP:
        raise MetaStoreError("app zip is missing or too large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise MetaStoreError("not a zip file") from exc
    infos = archive.infolist()
    if len(infos) > _MAX_SITE_ZIP_FILES:
        raise MetaStoreError("app zip has too many files")
    host_text = None
    folder = ""
    for info in infos:
        if info.is_dir():
            continue
        if info.file_size > _MAX_SITE_ZIP_MEMBER:
            raise MetaStoreError("app zip member too large")
        mapped = _zip_app_member(info.filename)
        if mapped is None:
            raise MetaStoreError("app zip has an unsafe path")
        member_slug, name = mapped
        if name != "host.json":
            continue
        host_text = archive.read(info).decode("utf-8")
        folder = member_slug
    if not host_text:
        raise MetaStoreError("app zip is missing host.json")
    try:
        host = json.loads(host_text)
    except json.JSONDecodeError as exc:
        raise MetaStoreError("host.json is not JSON") from exc
    if not isinstance(host, dict) or "description" not in host:
        raise MetaStoreError("host.json is missing description")
    if host.get("installer") is True or host.get("store") is True or host.get("binary") is True:
        raise MetaStoreError("store installers cannot be opened as a project")
    wanted = str(slug or host.get("slug") or folder or "").strip()
    desc = from_json(json.dumps(host.get("description")))
    artifact = instantiate(desc, target=TARGET_DESKTOP_HOST, slug=wanted)
    save_artifact(artifact, base=base)
    stored = apply_desktop_host(
        desc,
        slug=artifact.slug or wanted,
        data_root=base or data_dir(),
        parts=artifact.payload_object().get("parts") if artifact.payload_object() else None,
    )
    save_draft(artifact.slug, code=to_json(desc, indent=2), base=base)
    return {
        "binary": False,
        "code": to_json(desc, indent=2),
        "installer": False,
        "slug": artifact.slug,
        "store": False,
        "studio": f"/studio/meta/{artifact.slug}",
        "target": artifact.target,
        "zip_url": f"/api/builder-core/meta/apps/{artifact.slug}/zip",
        "host": stored.get("host"),
    }


def _zip_has_named_file(archive, wanted: str) -> bool:
    suffix = "/" + wanted
    for info in archive.infolist():
        name = str(info.filename or "").replace("\\", "/")
        if name == wanted or name.endswith(suffix):
            return True
    return False


def _zip_app_member(filename: str) -> tuple[str, str] | None:
    name = str(filename or "").replace("\\", "/")
    if name.startswith("/") or ":" in name:
        return None
    parts = [part for part in name.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return None
    if len(parts) == 1:
        return "", parts[0]
    if len(parts) != 2:
        return None
    try:
        folder = validate_slug(parts[0])
    except InstantiationError:
        return None
    return folder, parts[1]


def _zip_member_parts(filename: str) -> tuple[str, str] | None:
    name = str(filename or "").replace("\\", "/")
    if name.startswith("/") or ":" in name:
        return None
    parts = [part for part in name.split("/") if part]
    if len(parts) != 2 or any(part in {".", ".."} for part in parts):
        return None
    try:
        folder = validate_slug(parts[0])
    except InstantiationError:
        return None
    filename_only = parts[1]
    if filename_only == "meta.json" or filename_only == "index.html":
        return folder, filename_only
    if filename_only.endswith(".html"):
        try:
            validate_slug(filename_only[:-5])
        except InstantiationError:
            return None
        return folder, filename_only
    try:
        return folder, validate_asset_name(filename_only)
    except InstantiationError:
        return None


def list_artifacts(*, base: Path | None = None) -> list[dict]:
    root = artifacts_root(base)
    if not root.is_dir():
        return []
    rows = []
    for path in sorted(root.glob("*.json")):
        try:
            validate_slug(path.stem)
            artifact = load_artifact(path.stem, base=base)
        except (InstantiationError, MetaStoreError):
            continue
        row = {
            "checksum": artifact.checksum,
            "files": list_site_files(artifact.slug, base=base),
            "public_url": artifact.public_url,
            "slug": artifact.slug,
            "target": artifact.target,
        }
        if artifact.target == TARGET_WEB_BUILD:
            row["zip_url"] = f"/api/builder-core/meta/sites/{artifact.slug}/zip"
        rows.append(row)
    return rows


def save_draft(slug: str, *, code: str, events: str = "", base: Path | None = None, current: bool = True) -> dict:
    clean = validate_slug(slug)
    payload = {
        "code": str(code),
        "events": str(events or ""),
        "slug": clean,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _atomic_write(draft_path(clean, base), json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if current:
        _atomic_write(
            drafts_root(base) / CURRENT_POINTER,
            json.dumps({"slug": clean}, ensure_ascii=False, sort_keys=True),
        )
    index_upsert("draft", clean, str(code), updated_at=str(payload["updated_at"]), base=base)
    return payload


def draft_is_empty(code: str) -> bool:
    raw = str(code or "").strip()
    if not raw or raw in {"{}", "[]", "null"}:
        return True
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return data in ({}, [], None)


def load_draft(slug: str, *, base: Path | None = None) -> dict:
    path = draft_path(slug, base)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MetaStoreError(f"no draft for slug {slug!r}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MetaStoreError("cannot read draft") from exc
    if not isinstance(data, dict) or "code" not in data:
        raise MetaStoreError("draft is missing code")
    code = str(data.get("code") or "")
    return {
        "code": code,
        "empty": draft_is_empty(code),
        "events": str(data.get("events") or ""),
        "slug": str(data.get("slug") or slug),
        "updated_at": str(data.get("updated_at") or ""),
    }


def _desc_atom(node):
    if not isinstance(node, dict):
        return None
    if str(node.get("form") or "") == "atom":
        return node.get("value")
    return None


def _shot_from_desc(item: dict) -> dict | None:
    if not isinstance(item, dict) or str(item.get("form") or "") != "struct":
        return None
    fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
    cut_node = fields.get("cut") if isinstance(fields.get("cut"), dict) else {}
    nested = []
    if str(cut_node.get("form") or "") == "sequence":
        for child in cut_node.get("items") or []:
            row = _shot_from_desc(child) if isinstance(child, dict) else None
            if row:
                nested.append(row)
    inn = _desc_atom(fields.get("in"))
    out = _desc_atom(fields.get("out"))
    dur = _desc_atom(fields.get("duration"))
    return {
        "clip": str(_desc_atom(fields.get("clip")) or "shot"),
        "track": int(_desc_atom(fields.get("track")) or 1),
        "in": float(inn or 0),
        "out": float(out or 0),
        "duration": float(dur or 1),
        "edl": str(_desc_atom(fields.get("edl")) or ""),
        "cut": nested,
    }


def _drop_shot_audio(row: dict) -> dict:
    row.pop("audio", None)
    nested = row.get("cut")
    if isinstance(nested, list):
        cleaned = []
        for child in nested:
            if isinstance(child, dict):
                cleaned.append(_drop_shot_audio(child))
            else:
                cleaned.append(child)
        row["cut"] = cleaned
    return row


def nested_cut_from_draft(slug: str, *, base: Path | None = None) -> list[dict]:
    """Read a child EDL cut from a local draft under ZINTRIQ_DATA_DIR. One document only."""
    draft = load_draft(slug, base=base)
    raw = str(draft.get("code") or "").strip()
    if not raw:
        return []
    data = None
    if raw[0] in "{[":
        try:
            parsed = json.loads(raw)
            data = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            data = None
    if data is None:
        try:
            from meta.uir.yaml_desc import load_yaml

            parsed = load_yaml(raw)
            data = parsed if isinstance(parsed, dict) else None
        except Exception:
            return []
    if not isinstance(data, dict):
        return []
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
    # Ignore child Desc audio sequence; mix stays on this document's clips.
    if isinstance(fields, dict):
        fields = dict(fields)
        fields.pop("audio", None)
    shots_node = fields.get("shots") if isinstance(fields, dict) else None
    if not isinstance(shots_node, dict) or str(shots_node.get("form") or "") != "sequence":
        return []
    out = []
    for item in shots_node.get("items") or []:
        row = _shot_from_desc(item) if isinstance(item, dict) else None
        if row:
            out.append(_drop_shot_audio(row))
    return out


def current_draft_slug(*, base: Path | None = None) -> str | None:
    pointer = drafts_root(base) / CURRENT_POINTER
    if not pointer.is_file():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    slug = str((data or {}).get("slug") or "").strip()
    try:
        return validate_slug(slug)
    except InstantiationError:
        return None


def list_drafts(*, base: Path | None = None) -> list[dict]:
    root = drafts_root(base)
    if not root.is_dir():
        return []
    rows = []
    for path in sorted(root.glob("*.json")):
        if path.name == CURRENT_POINTER:
            continue
        try:
            rows.append(load_draft(path.stem, base=base))
        except (InstantiationError, MetaStoreError):
            continue
    rows.sort(key=lambda row: (str(row.get("updated_at") or ""), str(row.get("slug") or "")), reverse=True)
    return rows


def search_drafts(query: str, *, base: Path | None = None) -> list[dict]:
    return [hit for hit in search_all(query, base=base) if hit.get("kind") == "draft"]


def _doc_key(kind: str, slug: str) -> str:
    return f"{kind}:{slug}"


def _index_path(root: Path) -> Path:
    return root / "search-index.json"


def _read_index(root: Path) -> dict:
    path = _index_path(root)
    if not path.is_file():
        return {"docs": [], "inv": {}, "rev": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"docs": [], "inv": {}, "rev": {}}
    if not isinstance(data, dict):
        return {"docs": [], "inv": {}, "rev": {}}
    data.setdefault("docs", [])
    data.setdefault("inv", {})
    data.setdefault("rev", {})
    return data


def _write_index(root: Path, data: dict) -> None:
    _atomic_write(root / "search-index.json", json.dumps(data, ensure_ascii=False, sort_keys=True))


def index_upsert(
    kind: str,
    slug: str,
    text: str,
    *,
    target: str = "",
    updated_at: str = "",
    base: Path | None = None,
) -> dict:
    root = base or data_dir()
    data = _read_index(root)
    if data.get("docs") and not data.get("inv"):
        rebuild_search_index(base=root)
        data = _read_index(root)
    key = _doc_key(kind, slug)
    for tok in list(data.get("rev", {}).get(key) or []):
        bucket = list(data.get("inv", {}).get(tok) or [])
        data["inv"][tok] = [item for item in bucket if item != key]
    blob = f"{kind} {slug} {target} {text}"
    tokens = _tokens(blob)
    data.setdefault("rev", {})[key] = tokens
    inv = data.setdefault("inv", {})
    for tok in tokens:
        bucket = inv.setdefault(tok, [])
        if key not in bucket:
            bucket.append(key)
    docs = [row for row in data.get("docs") or [] if not (row.get("kind") == kind and row.get("slug") == slug)]
    docs.append(
        {
            "kind": kind,
            "slug": slug,
            "target": target,
            "text": str(text)[:80000],
            "updated_at": updated_at,
        }
    )
    data["docs"] = docs
    _write_index(root, data)
    return data


def _desc_meta(text: str) -> dict:
    from plugin_catalog import desc_fingerprint

    form = ""
    kind = ""
    meta_level = 0
    raw = str(text or "")
    fp = desc_fingerprint(raw)
    try:
        data = json.loads(raw) if raw.lstrip().startswith("{") else None
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        form = str(data.get("form") or "")
        fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
        if not form:
            form = str((fields.get("form") or {}).get("value") or "")
        kind_node = fields.get("kind") if isinstance(fields.get("kind"), dict) else {}
        kind = str(kind_node.get("value") or data.get("kind") or "")
        level_node = fields.get("meta_level") if isinstance(fields.get("meta_level"), dict) else {}
        try:
            meta_level = int(level_node.get("value") if level_node.get("value") is not None else data.get("meta_level") or 0)
        except (TypeError, ValueError):
            meta_level = 0
        if not form:
            form = str((fields.get("form") or {}).get("value") or "")
    return {"desc_kind": kind, "fingerprint": fp, "form": form, "meta_level": max(0, meta_level)}


def rebuild_search_index(*, base: Path | None = None) -> list[dict]:
    from plugin_catalog import desc_fingerprint, plugin_drafts

    root = base or data_dir()
    docs: list[dict] = []
    plugin_fps: set[str] = set()
    plugins = root / "plugins"
    if plugins.is_dir():
        for path in sorted(plugins.glob("*.json")):
            try:
                text = path.read_text(encoding="utf-8")
                pack = json.loads(text)
            except (OSError, json.JSONDecodeError):
                continue
            meta = _desc_meta(json.dumps(pack.get("document")) if isinstance(pack, dict) and pack.get("document") is not None else text[:8000])
            if meta.get("fingerprint"):
                plugin_fps.add(meta["fingerprint"])
            docs.append(
                {
                    "kind": "plugin",
                    "slug": path.stem if not isinstance(pack, dict) else str(pack.get("id") or path.stem),
                    "text": text[:8000],
                    "updated_at": "",
                    "stamped": True,
                    **meta,
                }
            )
    bound = plugin_drafts(root)
    bound_slugs = set(bound.values())
    for row in list_drafts(base=root):
        code = str(row.get("code") or "")
        meta = _desc_meta(code)
        stamped = bool(meta.get("fingerprint") and meta["fingerprint"] in plugin_fps) or str(row.get("slug") or "") in bound_slugs
        if stamped and meta.get("fingerprint") not in plugin_fps:
            stamped = str(row.get("slug") or "") in bound_slugs and bool(plugin_fps)
        docs.append(
            {
                "kind": "draft",
                "slug": row.get("slug"),
                "text": code[:80000],
                "updated_at": row.get("updated_at") or "",
                "stamped": bool(meta.get("fingerprint") in plugin_fps),
                **meta,
            }
        )
    for row in list_artifacts(base=root):
        extra = str(row.get("checksum") or "") + " " + str(row.get("target") or "")
        try:
            extra += " " + load_artifact(str(row.get("slug")), base=root).payload[:40000]
        except (MetaStoreError, InstantiationError, TypeError):
            pass
        docs.append(
            {
                "kind": "artifact",
                "slug": row.get("slug"),
                "target": row.get("target"),
                "text": extra,
                "updated_at": "",
                "stamped": False,
                **_desc_meta(""),
            }
        )
    last_open = root / "store" / "last-open.json"
    if last_open.is_file():
        try:
            opened = json.loads(last_open.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            opened = []
        if isinstance(opened, list):
            for row in opened:
                if not isinstance(row, dict):
                    continue
                text = str(row.get("text") or "")
                docs.append(
                    {
                        "kind": str(row.get("kind") or "zip"),
                        "slug": row.get("slug"),
                        "text": text[:8000],
                        "updated_at": "",
                        "stamped": False,
                        **_desc_meta(text),
                    }
                )
    inv: dict[str, list[str]] = {}
    rev: dict[str, list[str]] = {}
    for doc in docs:
        key = _doc_key(str(doc.get("kind") or ""), str(doc.get("slug") or ""))
        tokens = _tokens(
            str(doc.get("kind") or "")
            + " "
            + str(doc.get("slug") or "")
            + " "
            + str(doc.get("target") or "")
            + " "
            + str(doc.get("form") or "")
            + " "
            + str(doc.get("desc_kind") or "")
            + " "
            + str(doc.get("fingerprint") or "")
            + " "
            + str(doc.get("text") or "")
        )
        rev[key] = tokens
        for tok in tokens:
            bucket = inv.setdefault(tok, [])
            if key not in bucket:
                bucket.append(key)
    _write_index(root, {"docs": docs, "inv": inv, "rev": rev})
    return docs


def search_all(
    query: str,
    *,
    form: str = "",
    kind: str = "",
    fingerprint: str = "",
    stamped: str = "",
    meta_level: str = "",
    meta_level_min: str = "",
    meta_level_max: str = "",
    sql: str = "",
    base: Path | None = None,
) -> list[dict]:
    if str(sql or "").strip():
        raise MetaStoreError("arbitrary SQL is not allowed")
    needle = str(query or "").strip().lower()
    root = base or data_dir()
    path = _index_path(root)
    if not path.is_file():
        rebuild_search_index(base=root)
    data = _read_index(root)
    if data.get("docs") and not data.get("inv"):
        rebuild_search_index(base=root)
        data = _read_index(root)
    docs = [row for row in data.get("docs") or [] if isinstance(row, dict)]
    if needle:
        tokens = _tokens(needle)
        keys = None
        inv = data.get("inv") or {}
        if tokens and inv:
            for tok in tokens:
                bucket = lookup(inv, tok)
                keys = bucket if keys is None else keys & bucket
            if keys is not None:
                wanted = keys
                docs = [row for row in docs if _doc_key(str(row.get("kind") or ""), str(row.get("slug") or "")) in wanted]
        else:
            docs = [
                row
                for row in docs
                if needle
                in (
                    str(row.get("kind") or "")
                    + " "
                    + str(row.get("slug") or "")
                    + " "
                    + str(row.get("target") or "")
                    + " "
                    + str(row.get("form") or "")
                    + " "
                    + str(row.get("desc_kind") or "")
                    + " "
                    + str(row.get("fingerprint") or "")
                    + " "
                    + str(row.get("text") or "")
                ).lower()
            ]
    want_form = str(form or "").strip().lower()
    want_kind = str(kind or "").strip().lower()
    want_fp = str(fingerprint or "").strip().lower()
    want_stamped = str(stamped or "").strip().lower()
    want_level = str(meta_level or "").strip()
    want_min = str(meta_level_min or "").strip()
    want_max = str(meta_level_max or "").strip()
    if want_form:
        docs = [row for row in docs if str(row.get("form") or "").lower() == want_form]
    if want_kind:
        docs = [row for row in docs if str(row.get("desc_kind") or "").lower() == want_kind]
    if want_fp:
        docs = [row for row in docs if str(row.get("fingerprint") or "").lower().startswith(want_fp)]
    if want_stamped in {"0", "false", "unstamped", "no"}:
        docs = [row for row in docs if not row.get("stamped")]
    elif want_stamped in {"1", "true", "stamped", "yes"}:
        docs = [row for row in docs if row.get("stamped")]
    if want_level != "":
        try:
            level = int(want_level)
        except (TypeError, ValueError):
            level = None
        if level is not None:
            docs = [row for row in docs if int(row.get("meta_level") or 0) == level]
    if want_min != "":
        try:
            low = int(want_min)
        except (TypeError, ValueError):
            low = None
        if low is not None:
            docs = [row for row in docs if int(row.get("meta_level") or 0) >= low]
    if want_max != "":
        try:
            high = int(want_max)
        except (TypeError, ValueError):
            high = None
        if high is not None:
            docs = [row for row in docs if int(row.get("meta_level") or 0) <= high]
    hits = []
    for doc in docs:
        hits.append(
            {
                "kind": doc.get("kind"),
                "slug": doc.get("slug"),
                "target": doc.get("target"),
                "updated_at": doc.get("updated_at") or "",
                "form": doc.get("form") or "",
                "desc_kind": doc.get("desc_kind") or "",
                "fingerprint": doc.get("fingerprint") or "",
                "stamped": bool(doc.get("stamped")),
                "meta_level": int(doc.get("meta_level") or 0),
            }
        )
    return hits


def load_layout(*, base: Path | None = None) -> dict:
    root = base or data_dir()
    path = root / "workbench-layout.json"
    if not path.is_file():
        return {"groups": [], "version": 2}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"groups": [], "version": 2}
    return normalize_layout(data) if isinstance(data, dict) and data else {"groups": [], "version": 2}


def save_layout(layout: dict, *, base: Path | None = None) -> dict:
    root = base or data_dir()
    payload = normalize_layout(layout if isinstance(layout, dict) else {})
    _atomic_write(root / "workbench-layout.json", json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


def taken_slugs(*, base: Path | None = None) -> set[str]:
    names: set[str] = set()
    for row in list_drafts(base=base):
        names.add(str(row.get("slug") or ""))
    for row in list_artifacts(base=base):
        names.add(str(row.get("slug") or ""))
    sites = sites_root(base)
    if sites.is_dir():
        for path in sites.iterdir():
            if not path.is_dir():
                continue
            try:
                names.add(validate_slug(path.name))
            except InstantiationError:
                continue
    names.discard("")
    return names


def unused_slug(prefix: str = "site", *, base: Path | None = None) -> str:
    free, _occupied = unused_slug_with_chain(prefix, base=base)
    return free


def unused_slug_with_chain(prefix: str = "site", *, base: Path | None = None) -> tuple[str, list[str]]:
    """Return (free slug, occupied names tried before it) for rename conflict preview."""
    stem = validate_slug(prefix)
    taken = taken_slugs(base=base)
    occupied: list[str] = []
    if stem not in taken:
        return stem, occupied
    occupied.append(stem)
    for index in range(2, 10000):
        candidate = f"{stem}-{index}"
        if candidate not in taken:
            return validate_slug(candidate), occupied
        occupied.append(candidate)
    raise MetaStoreError("no unused slug")


def free_slug_slots(prefix: str = "site", *, base: Path | None = None, limit: int = 5) -> list[str]:
    """Next free rename targets after occupied prefix chain (pickable slots)."""
    stem = validate_slug(prefix)
    taken = taken_slugs(base=base)
    slots: list[str] = []
    if stem not in taken:
        slots.append(stem)
    index = 2
    while len(slots) < max(1, int(limit or 5)) and index < 10000:
        candidate = f"{stem}-{index}"
        if candidate not in taken:
            slots.append(validate_slug(candidate))
        index += 1
    return slots


class DraftSlugTaken(MetaStoreError):
    """Rename target exists; carry a free suggestion."""

    def __init__(
        self,
        message: str,
        *,
        suggestion: str = "",
        conflict_chain: list[str] | None = None,
        free_slots: list[str] | None = None,
    ):
        super().__init__(message)
        self.suggestion = suggestion
        self.conflict_chain = list(conflict_chain or [])
        self.free_slots = list(free_slots or ([] if not suggestion else [suggestion]))


def rename_draft(old_slug: str, new_slug: str, *, base: Path | None = None) -> dict:
    """Rename a draft file and keep current pointer / plugin bindings."""
    old = validate_slug(old_slug)
    new = validate_slug(new_slug)
    if old == new:
        return load_draft(old, base=base)
    if draft_path(new, base).is_file() or new in taken_slugs(base=base):
        suggest, chain = unused_slug_with_chain(new, base=base)
        slots = free_slug_slots(new, base=base, limit=5)
        raise DraftSlugTaken(
            "slug taken",
            suggestion=suggest,
            conflict_chain=chain,
            free_slots=slots,
        )
    draft = load_draft(old, base=base)
    was_current = current_draft_slug(base=base) == old
    save_draft(new, code=draft["code"], events=draft.get("events") or "", current=was_current, base=base)
    from plugin_catalog import plugin_drafts, remember_plugin_draft

    root = base or data_dir()
    for pack_id, bound in list(plugin_drafts(root).items()):
        if bound == old:
            remember_plugin_draft(root, pack_id, new)
    delete_draft(old, base=base)
    return load_draft(new, base=base)


def fill_draft_skeleton(
    slug: str,
    *,
    pack_id: str = "",
    base: Path | None = None,
) -> dict:
    """Write the primary installed plugin Desc into an existing (usually empty) draft."""
    from plugin_catalog import (
        PluginError,
        catalog,
        installed_index,
        pack_document_code,
        pack_view_id,
        primary_installed_pack,
        remember_plugin_draft,
    )

    root = base or data_dir()
    clean = validate_slug(slug)
    load_draft(clean, base=root)
    wanted = str(pack_id or "").strip()
    pack = None
    if wanted and wanted not in {"auto", "primary"}:
        pack = next((row for row in catalog(include_pending=True, data_root=root) if row.get("id") == wanted), None)
    if pack is None:
        pack = primary_installed_pack(root)
    if not pack:
        raise MetaStoreError("install a view pack from Community first")
    ident = str(pack.get("id") or "")
    try:
        code = pack_document_code(pack)
    except (PluginError, TypeError, ValueError) as exc:
        raise MetaStoreError(str(exc)) from exc
    payload = save_draft(clean, code=code, current=True, base=root)
    if ident in set(installed_index(root)):
        remember_plugin_draft(root, ident, clean)
    out = load_draft(clean, base=root)
    out["pack_id"] = ident
    out["pane"] = pack_view_id(pack) or ""
    out["filled"] = True
    out["updated_at"] = payload.get("updated_at") or out.get("updated_at")
    return out


def _delete_under(root: Path, target: Path) -> bool:
    try:
        base = root.resolve()
        resolved = target.resolve()
    except OSError as exc:
        raise MetaStoreError("cannot delete") from exc
    if resolved != base and base not in resolved.parents:
        raise MetaStoreError("refusing to delete outside data dir")
    if resolved.is_file():
        resolved.unlink()
        return True
    if resolved.is_dir():
        shutil.rmtree(resolved)
        return True
    return False


def delete_draft(slug: str, *, base: Path | None = None) -> str:
    clean = validate_slug(slug)
    root = drafts_root(base)
    path = draft_path(clean, base)
    if not _delete_under(root, path):
        raise MetaStoreError("no such draft")
    pointer = root / CURRENT_POINTER
    if current_draft_slug(base=base) == clean:
        if pointer.is_file():
            _delete_under(root, pointer)
        remaining = list_drafts(base=base)
        if remaining:
            _atomic_write(
                pointer,
                json.dumps({"slug": remaining[0]["slug"]}, ensure_ascii=False, sort_keys=True),
            )
    rebuild_search_index(base=base)
    return clean


def delete_site(slug: str, *, base: Path | None = None) -> str:
    clean = validate_slug(slug)
    missing = True
    art = artifact_path(clean, base)
    if art.is_file() and _delete_under(artifacts_root(base), art):
        missing = False
    site = sites_root(base) / clean
    if site.is_dir() and _delete_under(sites_root(base), site):
        missing = False
    assets = assets_root(base) / clean
    if assets.is_dir() and _delete_under(assets_root(base), assets):
        missing = False
    if missing:
        raise MetaStoreError("no such site")
    return clean


def studio_index(*, base: Path | None = None) -> dict:
    """Drafts and artifacts for Studio chrome. Empty if the data dir is unset."""
    try:
        root = base or data_dir()
    except MetaStoreError:
        return {"artifacts": [], "current": None, "drafts": []}
    return {
        "artifacts": list_artifacts(base=root),
        "current": current_draft_slug(base=root),
        "drafts": list_drafts(base=root),
    }


def _sniff_image(data: bytes) -> str:
    raw = bytes(data or b"")
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    raise MetaStoreError("not a local image")


def _asset_dir(slug: str, *, base: Path | None = None) -> Path:
    return assets_root(base) / validate_slug(slug)


def list_assets(slug: str, *, base: Path | None = None) -> list[str]:
    root = _asset_dir(slug, base=base)
    if not root.is_dir():
        return []
    names = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.parent != root:
            continue
        try:
            names.append(validate_asset_name(path.name))
        except InstantiationError:
            continue
    return names


def asset_path(slug: str, name: str, *, base: Path | None = None) -> Path:
    return _asset_dir(slug, base=base) / validate_asset_name(name)


def save_asset(slug: str, name: str, data: bytes, *, base: Path | None = None) -> str:
    blob = bytes(data or b"")
    if not blob or len(blob) > _ASSET_MAX:
        raise MetaStoreError("image is missing or too large")
    sniffed = _sniff_image(blob)
    try:
        clean = validate_asset_name(name)
    except InstantiationError:
        ext = "jpeg" if str(name).lower().endswith(".jpeg") and sniffed == "jpg" else sniffed
        clean = validate_asset_name(f"image.{ext}")
    ext = clean.rsplit(".", 1)[-1]
    if ext == "jpeg":
        ext = "jpg"
    if sniffed != ext:
        raise MetaStoreError("image type must match the file name")
    existing = list_assets(slug, base=base)
    if clean not in existing and len(existing) >= _ASSET_MAX_COUNT:
        raise MetaStoreError("too many images")
    path = asset_path(slug, clean, base=base)
    _atomic_write_bytes(path, blob)
    site = sites_root(base) / validate_slug(slug)
    if site.is_dir():
        _atomic_write_bytes(site / clean, blob)
    return clean


def delete_asset(slug: str, name: str, *, base: Path | None = None) -> str:
    clean = validate_asset_name(name)
    folder = _asset_dir(slug, base=base)
    path = folder / clean
    site_root = sites_root(base) / validate_slug(slug)
    site_copy = site_root / clean
    missing = True
    if path.is_file() and path.parent == folder:
        path.unlink()
        missing = False
    if site_copy.is_file() and site_copy.parent == site_root:
        site_copy.unlink()
        missing = False
    if missing:
        raise MetaStoreError("no such image")
    return clean


def asset_data_url(slug: str, name: str, *, base: Path | None = None) -> str:
    try:
        path = asset_path(slug, name, base=base)
    except InstantiationError:
        return ""
    if not path.is_file():
        return ""
    ext = path.name.rsplit(".", 1)[-1]
    mime = _ASSET_MIME.get(ext) or "application/octet-stream"
    import base64

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _copy_assets_into_site(slug: str, root: Path, *, base: Path | None = None) -> None:
    for name in list_assets(slug, base=base):
        src = asset_path(slug, name, base=base)
        if src.is_file():
            _atomic_write_bytes(root / name, src.read_bytes())


def _site_member_bytes(root: Path, name: str, *, slug: str, base: Path | None = None) -> bytes:
    try:
        asset_name = validate_asset_name(name)
    except InstantiationError:
        asset_name = ""
    if asset_name:
        path = asset_path(slug, asset_name, base=base)
        if path.is_file():
            return path.read_bytes()
        site_copy = root / asset_name
        if site_copy.is_file():
            return site_copy.read_bytes()
        raise MetaStoreError(f"missing image {asset_name}")
    return (root / name).read_bytes()


def application_asset_response(slug: str, name: str) -> Response | None:
    """Serve a stored local image at /build/<slug>/assets/<name>."""
    if not desktop_enabled():
        return None
    try:
        path = asset_path(slug, name)
    except (InstantiationError, MetaStoreError):
        return None
    if not path.is_file():
        return None
    ext = path.name.rsplit(".", 1)[-1]
    response = Response(path.read_bytes(), mimetype=_ASSET_MIME.get(ext, "application/octet-stream"))
    response.headers["Cache-Control"] = "no-store"
    return response


def application_page_response(slug: str, page_key: str | None = None) -> Response | None:
    """Serve a stored software.page at /build/<slug>/… when desktop is on."""
    if not desktop_enabled():
        return None
    try:
        artifact = load_artifact(slug)
    except (MetaStoreError, InstantiationError):
        return None
    from flask import session
    from meta.instantiation import TARGET_WEB_BUILD, render_software_page
    from meta.instantiation.system import part_artifact_at

    if artifact.target != TARGET_WEB_BUILD:
        response = Response(artifact.payload, mimetype=artifact.media_type or "application/json")
        response.headers["Cache-Control"] = "no-store"
        return response

    child = part_artifact_at(artifact, page_key)
    if child is not None and child.target != TARGET_WEB_BUILD:
        response = Response(child.payload, mimetype=child.media_type or "application/json")
        response.headers["Cache-Control"] = "no-store"
        return response

    csrf = ""
    try:
        csrf = str(session.get("csrf_token") or "")
    except RuntimeError:
        csrf = ""
    try:
        page = render_software_page(
            artifact,
            step_action=f"/api/builder-core/meta/page/{validate_slug(slug)}/step",
            csrf_token=csrf,
            page_key=page_key,
        )
    except InstantiationError:
        return None
    from builder_kernel.csp import BUILD_CSP

    response = Response(page, mimetype="text/html")
    response.headers["Content-Security-Policy"] = BUILD_CSP
    response.headers["Cache-Control"] = "no-store"
    return response
