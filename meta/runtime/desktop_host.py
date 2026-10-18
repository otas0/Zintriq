"""Compile a meta.system onto the existing Electron + local Flask host.

Same stack. Not Unity, not a second IDE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from meta.description import to_json
from meta.description.composite import StructDesc
from meta.description.types import AtomDesc, Desc
from meta.instantiation.errors import InstantiationError
from meta.instantiation.system import SYSTEM_KIND, child_for_part_kind, software_system

STUDIO_PATH = "/studio"
HOST_BIND = "127.0.0.1"
HOST_STACK = ("electron", "flask")
ELECTRON_MAIN = "desktop/main.js"
FLASK_ENTRY = "app.py"
APP_ID = "com.zintriq.studio"

# Files the existing Electron packager already ships. Recipe only — no builder run.
HOST_FILES = (
    "desktop/main.js",
    "desktop/preload.js",
    "desktop/flask_host.js",
    "desktop/navigation.js",
    "desktop/meta_http.js",
    "app.py",
    "meta/",
    "plugin_catalog.py",
)

# Pack plugin id → system part kind. Keys are URL slugs (no dots).
EDITOR_PARTS: tuple[tuple[str, str, str], ...] = (
    ("scene", "Scene", "scene"),
    ("node", "Node", "node.graph"),
    ("ui", "UI", "page"),
    ("animation", "Animation", "animation"),
    ("shader", "Shader", "shader"),
    ("audio", "Audio", "audio"),
    ("level", "Level", "level"),
    ("data", "Data", "data.table"),
    ("logic", "Logic", "logic"),
    ("text", "Text", "text"),
    ("vector", "Vector", "vector"),
    ("bitmap", "Bitmap", "bitmap"),
    ("model3d", "Model 3D", "model3d"),
    ("material", "Material", "material"),
    ("particle", "Particle", "particle"),
    ("terrain", "Terrain", "terrain"),
    ("video", "Video", "video"),
    ("font", "Font", "font"),
    ("document", "Document", "document"),
    ("spreadsheet", "Spreadsheet", "spreadsheet"),
    ("map", "Map", "map"),
    ("circuit", "Circuit", "circuit"),
    ("chip", "Chip", "chip"),
    ("quantum", "Quantum", "quantum"),
    ("ai", "AI", "ai"),
    ("cad", "CAD", "cad.solid"),
    ("checkout", "Checkout", "commerce.checkout"),
    ("channel", "Channel", "social.channel"),
    ("broadcast", "Broadcast", "media.channel"),
    ("physics", "Physics", "physics.body"),
    ("skeleton", "Skeleton", "skeleton.rig"),
    ("film", "Film", "film.cut"),
    ("brep", "B-rep", "cad.brep"),
    ("settle", "Settle", "commerce.settle"),
    ("federate", "Federate", "social.federate"),
    ("weights", "Weights", "llm.weights"),
    ("vr", "VR", "vr.space"),
    ("robotics", "Robotics", "robotics.cell"),
    ("print3d", "Print 3D", "print3d.job"),
    ("cnc", "CNC", "cnc.job"),
    ("chain", "Chain", "chain.ledger"),
)


def editor_plugin_ids() -> list[str]:
    return [row[0] for row in EDITOR_PARTS]


def pack_spec(*, slug: str = "", title: str = "") -> dict[str, Any]:
    """Unsigned local pack recipe. Does not emit a second binary or installer."""
    return {
        "appId": APP_ID,
        "binary": False,
        "command": ["npm", "run", "pack"],
        "cwd": "desktop",
        "dir": True,
        "files": list(HOST_FILES),
        "installer": False,
        "main": ELECTRON_MAIN,
        "product": title or "Zintriq Studio",
        "publish": "never",
        "signed": False,
        "slug": slug,
        "unity": False,
    }


def launch_spec(
    *,
    slug: str = "",
    editors: list[str] | None = None,
    data_dir: str = "",
) -> dict[str, Any]:
    ids = list(editors) if editors is not None else editor_plugin_ids()
    return {
        "bind": HOST_BIND,
        "data_dir": data_dir,
        "editors": ids,
        "electron": ELECTRON_MAIN,
        "env": {
            "ZINTRIQ_DESKTOP": "1",
            "ZINTRIQ_HOST": HOST_BIND,
        },
        "flask": FLASK_ENTRY,
        "loopback": True,
        "loopback_only": True,
        "pack_dir": {
            "command": ["npm", "run", "pack"],
            "dir": True,
            "publish": "never",
            "signed": False,
        },
        "slug": slug,
        "studio": STUDIO_PATH,
        "token_env": "ZINTRIQ_DESKTOP_TOKEN",
        "wan": False,
    }


def host_spec(*, slug: str = "", title: str = "", data_dir: str = "") -> dict[str, Any]:
    editors = editor_plugin_ids()
    return {
        "bind": HOST_BIND,
        "editors": editors,
        "launch": launch_spec(slug=slug, editors=editors, data_dir=data_dir),
        "pack": pack_spec(slug=slug, title=title),
        "slug": slug,
        "stack": list(HOST_STACK),
        "studio": STUDIO_PATH,
        "title": title or "Zintriq",
        "unity": False,
        "wan": False,
    }


def recipe_checksum(payload: dict[str, Any]) -> str:
    host = payload.get("host") if isinstance(payload.get("host"), dict) else {}
    parts = payload.get("parts") if isinstance(payload.get("parts"), list) else []
    body = json.dumps(
        {
            "appId": APP_ID,
            "editors": host.get("editors") or [],
            "files": list(HOST_FILES),
            "parts": [row.get("key") for row in parts if isinstance(row, dict)],
            "studio": STUDIO_PATH,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def zintriq_system_desc() -> StructDesc:
    """Zintriq as a meta.system: workbench, loopback Flask, view plugins."""
    from meta.runtime.structure_systems import tag_system

    parts: list[tuple[str, str, Desc]] = [
        ("workbench", "Workbench", child_for_part_kind("os", title="Workbench")),
        ("flask", "Flask", child_for_part_kind("os", title="Flask 127.0.0.1")),
    ]
    for key, title, kind in EDITOR_PARTS:
        parts.append((key, title, child_for_part_kind(kind, title=title)))
    return tag_system(software_system(title="Zintriq", parts=parts), form="studio")


def desktop_artifact_body(desc: Desc, slug: str | None = None, *, parts: list | None = None) -> dict[str, Any]:
    if not isinstance(desc, StructDesc):
        raise InstantiationError("desktop_host requires a struct")
    fields = dict(desc.fields)
    kind = fields.get("kind")
    kind_name = ""
    if isinstance(kind, AtomDesc) and kind.has_value:
        kind_name = str(kind.value or "")
    title_node = fields.get("title")
    title = ""
    if isinstance(title_node, AtomDesc) and title_node.has_value:
        title = str(title_node.value or "")
    clean = str(slug or "").strip()
    host = host_spec(slug=clean, title=title or "Zintriq")
    if parts is not None:
        keys = [str(row.get("key") or "") for row in parts if isinstance(row, dict) and row.get("key")]
        editors = [key for key in keys if key not in {"workbench", "flask"}]
        host["editors"] = editors
        host["launch"] = launch_spec(slug=clean, editors=editors)
    payload = {
        "binary": False,
        "description": json.loads(to_json(desc)),
        "host": host,
        "installer": False,
        "kind": kind_name or SYSTEM_KIND,
        "launch": host["launch"],
        "pack": host["pack"],
        "parts": parts or [],
        "self": title.strip().lower() == "zintriq" or clean == "zintriq",
        "signed": False,
        "slug": clean,
        "studio": STUDIO_PATH,
        "unity": False,
        "cdn": False,
        "loop": "plugin-project-plugin",
        "wan": False,
    }
    payload["checksum"] = recipe_checksum(payload)
    return payload


def apply_desktop_host(desc: Desc, *, slug: str, data_root: Path, parts: list | None = None) -> dict[str, Any]:
    payload = desktop_artifact_body(desc, slug, parts=parts)
    folder = Path(data_root) / "desktop" / str(slug or "zintriq")
    folder.mkdir(parents=True, exist_ok=True)
    payload["launch"]["data_dir"] = str(folder)
    payload["host"]["launch"]["data_dir"] = str(folder)
    payload["checksum"] = recipe_checksum(payload)
    (folder / "host.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (folder / "pack.json").write_text(json.dumps(payload["pack"], indent=2), encoding="utf-8")
    (folder / "launch.json").write_text(json.dumps(payload["launch"], indent=2), encoding="utf-8")
    (folder / "checksum.txt").write_text(payload["checksum"] + "\n", encoding="utf-8")
    env_lines = [
        "# Local host recipe. Not an installer. Token is generated at process start.",
        "ZINTRIQ_DESKTOP=1",
        f"ZINTRIQ_HOST={HOST_BIND}",
    ]
    (folder / "env.desktop").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    (folder / "README.txt").write_text(
        "Local app pack. Not a store installer. Open Zintriq on this computer and use File → Open, or keep this folder next to ZINTRIQ_DATA_DIR.\n",
        encoding="utf-8",
    )
    return payload
