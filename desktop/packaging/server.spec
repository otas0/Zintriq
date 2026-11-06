# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for the thin editor Flask host. UPX off."""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]

datas = [
    (str(ROOT / "templates"), "templates"),
    (str(ROOT / "static"), "static"),
    (str(ROOT / "docs" / "THIRD_PARTY_NOTICES.md"), "docs"),
]

hiddenimports = [
    "waitress",
    "waitress.server",
    "waitress.task",
    "waitress.channel",
    "waitress.adjustments",
    "waitress.parser",
    "waitress.proxy_headers",
    "flask",
    "jinja2",
    "jinja2.ext",
    "markupsafe",
    "werkzeug",
    "itsdangerous",
    "click",
    "editor",
    "editor.changes",
    "editor.permissions",
    "editor.ai_bypass",
    "editor.ai_worker",
    "editor.git_ops",
    "editor.lsp_bridge",
    "editor.lsp_client",
    "editor.search",
    "editor.terminal",
    "editor.pty_session",
]

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="server",
)
