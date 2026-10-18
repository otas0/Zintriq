#!/usr/bin/env python3
"""Verify three-platform installer definitions without building binaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pkg = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))
    scripts = pkg.get("scripts") or {}
    build = pkg.get("build") or {}
    errors: list[str] = []
    for key in ("dist", "dist:mac", "dist:win", "dist:linux", "pack"):
        if key not in scripts:
            errors.append(f"package.json missing script {key}")
    mac = build.get("mac") or {}
    win = build.get("win") or {}
    linux = build.get("linux") or {}
    if "dmg" not in str(mac.get("target")):
        errors.append("mac target must include dmg")
    if "nsis" not in str(win.get("target")) and "portable" not in str(win.get("target")):
        errors.append("win target must include nsis or portable")
    if "AppImage" not in str(linux.get("target")) and "deb" not in str(linux.get("target")):
        errors.append("linux target must include AppImage or deb")
    workflow = (ROOT / ".github" / "workflows" / "desktop-pack.yml").read_text(encoding="utf-8")
    for needle in ("macos-latest", "windows-latest", "ubuntu-24.04", "npm run dist"):
        if needle not in workflow:
            errors.append(f"desktop-pack.yml missing {needle}")
    files = build.get("files") or []
    for name in ("main.js", "preload.js", "flask_host.js"):
        if name not in files:
            errors.append(f"build.files missing {name}")
    assocs = build.get("fileAssociations") or []
    by_ext = {}
    for item in assocs:
        if isinstance(item, dict) and item.get("ext"):
            by_ext[str(item.get("ext"))] = item
    for ext in ("zintriq-plugin.json", "zip"):
        row = by_ext.get(ext)
        if not row:
            errors.append(f"fileAssociations missing {ext}")
        elif str(row.get("rank") or "") != "Alternate":
            errors.append(f"{ext} association must be Alternate")
    smoke = (ROOT / "desktop" / "scripts" / "smoke.js").read_text(encoding="utf-8")
    if "assertAssocOpen" not in smoke or "zintriq-plugin.json" not in smoke:
        errors.append("smoke.js must open Alternate zintriq-plugin.json on pack artifacts")
    if "probeInstalledAssocs" not in smoke:
        errors.append("smoke.js must probe installed Alternate associations")
    assoc_os = (ROOT / "desktop" / "scripts" / "assoc-os.js").read_text(encoding="utf-8")
    for needle in ("mdls", "xdg-mime", "HKCU", "ZINTRIQ_SMOKE_NSIS", "OpenWithProgids", "Archive Utility"):
        if needle not in assoc_os:
            errors.append(f"assoc-os.js missing {needle}")
    pack_doc = (ROOT / "docs" / "desktop-packaging.md").read_text(encoding="utf-8")
    for needle in ("手测录像核对", "访达核对", "mime 核对", "OpenWithProgids", "Archive Utility", "对照文档"):
        if needle not in pack_doc:
            errors.append(f"desktop-packaging.md missing {needle}")
    pack_yml = (ROOT / ".github" / "workflows" / "desktop-pack.yml").read_text(encoding="utf-8")
    if "NSIS HKCU" not in pack_yml or "xdg-mime" not in pack_yml:
        errors.append("desktop-pack.yml must run NSIS HKCU and linux xdg-mime Alternate probes")
    if errors:
        for item in errors:
            print(item, file=sys.stderr)
        return 1
    print("acceptance pack check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
