"""Multi-language, hardware, and debug-extension registry for Zintriq."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Language / adapter catalog
# ---------------------------------------------------------------------------

LANGUAGE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "python",
        "label": "Python",
        "extensions": [".py", ".pyw"],
        "type": "python",
        "adapter": ["python", "-m", "debugpy.adapter"],
        "which": ["python3", "python"],
    },
    {
        "id": "node",
        "label": "JavaScript / Node",
        "extensions": [".js", ".mjs", ".cjs"],
        "type": "node",
        "adapter": "cdp",
        "which": ["node"],
    },
    {
        "id": "typescript",
        "label": "TypeScript",
        "extensions": [".ts", ".tsx"],
        "type": "node",
        "adapter": "cdp",
        "runtimeArgs": ["-r", "ts-node/register"],
        "which": ["node", "ts-node"],
    },
    {
        "id": "go",
        "label": "Go",
        "extensions": [".go"],
        "type": "custom",
        "adapter": ["dlv", "dap"],
        "which": ["dlv", "go"],
    },
    {
        "id": "rust",
        "label": "Rust",
        "extensions": [".rs"],
        "type": "custom",
        "adapter": ["codelldb"],
        "altAdapter": ["rust-gdb", "--interpreter=mi"],
        "which": ["codelldb", "rust-gdb", "lldb"],
    },
    {
        "id": "c_cpp",
        "label": "C / C++",
        "extensions": [".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"],
        "type": "custom",
        "adapter": ["gdb", "--interpreter=mi"],
        "altAdapter": ["lldb-mi"],
        "which": ["gdb", "lldb-mi", "lldb"],
    },
    {
        "id": "java",
        "label": "Java",
        "extensions": [".java"],
        "type": "custom",
        "adapter": ["java", "-jar", "jdt.ls.debug.jar"],  # placeholder; extension supplies real
        "which": ["java"],
        "hint": "Install Java debug extension or set debugAdapter to vscode-java-debug",
    },
    {
        "id": "csharp",
        "label": "C# / .NET",
        "extensions": [".cs"],
        "type": "custom",
        "adapter": ["netcoredbg", "--interpreter=vscode"],
        "which": ["netcoredbg", "dotnet"],
    },
    {
        "id": "kotlin",
        "label": "Kotlin",
        "extensions": [".kt", ".kts"],
        "type": "custom",
        "adapter": ["kotlin-debug-adapter"],
        "which": ["kotlin"],
    },
    {
        "id": "swift",
        "label": "Swift",
        "extensions": [".swift"],
        "type": "custom",
        "adapter": ["lldb-dap"],
        "which": ["lldb", "swift"],
    },
    {
        "id": "ruby",
        "label": "Ruby",
        "extensions": [".rb"],
        "type": "custom",
        "adapter": ["rdbg", "--open", "--port", "0"],
        "which": ["rdbg", "ruby"],
    },
    {
        "id": "php",
        "label": "PHP",
        "extensions": [".php"],
        "type": "custom",
        "adapter": ["php", "vendor/bin/phpadapter"],
        "which": ["php"],
        "hint": "Use xdebug + vscode-php-debug style adapter via extension",
    },
    {
        "id": "zig",
        "label": "Zig",
        "extensions": [".zig"],
        "type": "custom",
        "adapter": ["lldb-dap"],
        "which": ["zig", "lldb"],
    },
    {
        "id": "wasm",
        "label": "WebAssembly",
        "extensions": [".wasm", ".wat"],
        "type": "wasm",
        "adapter": "cdp",
        "which": ["node", "wasm-ld"],
    },
]


HARDWARE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "openocd-arm",
        "label": "ARM Cortex (OpenOCD + GDB)",
        "family": "arm",
        "type": "custom",
        "request": "attach",
        "debugAdapter": ["gdb-multiarch", "--interpreter=mi"],
        "miDebuggerServerAddress": "localhost:3333",
        "preLaunchTask": "openocd",
        "device": "cortex-m",
        "hint": "Start OpenOCD then attach; set svdPath for peripheral view",
    },
    {
        "id": "stm32",
        "label": "STM32 (OpenOCD)",
        "family": "arm",
        "type": "custom",
        "request": "launch",
        "debugAdapter": ["arm-none-eabi-gdb", "--interpreter=mi"],
        "configFiles": ["interface/stlink.cfg", "target/stm32f4x.cfg"],
        "device": "stm32",
    },
    {
        "id": "esp32",
        "label": "ESP32 (esp-idf / OpenOCD)",
        "family": "xtensa",
        "type": "custom",
        "request": "attach",
        "debugAdapter": ["xtensa-esp32-elf-gdb", "--interpreter=mi"],
        "miDebuggerServerAddress": "localhost:3333",
        "device": "esp32",
    },
    {
        "id": "rp2040",
        "label": "Raspberry Pi Pico (RP2040)",
        "family": "arm",
        "type": "custom",
        "request": "launch",
        "debugAdapter": ["arm-none-eabi-gdb", "--interpreter=mi"],
        "device": "rp2040",
        "hint": "Use picoprobe / openocd rp2040.cfg",
    },
    {
        "id": "avr",
        "label": "AVR (avrdude + avr-gdb)",
        "family": "avr",
        "type": "custom",
        "request": "attach",
        "debugAdapter": ["avr-gdb", "--interpreter=mi"],
        "device": "avr",
    },
    {
        "id": "riscv",
        "label": "RISC-V (OpenOCD / spike)",
        "family": "riscv",
        "type": "custom",
        "request": "attach",
        "debugAdapter": ["riscv64-unknown-elf-gdb", "--interpreter=mi"],
        "miDebuggerServerAddress": "localhost:3333",
        "device": "riscv",
    },
    {
        "id": "cuda",
        "label": "CUDA / GPU (cuda-gdb)",
        "family": "gpu",
        "type": "custom",
        "request": "launch",
        "debugAdapter": ["cuda-gdb", "--interpreter=mi"],
        "program": "${workspaceFolder}/a.out",
        "device": "cuda",
        "env": {"CUDA_VISIBLE_DEVICES": "0"},
    },
    {
        "id": "android",
        "label": "Android (lldb / JDWP)",
        "family": "mobile",
        "type": "custom",
        "request": "attach",
        "debugAdapter": ["lldb-dap"],
        "hint": "adb forward tcp:5039 jdwp:<pid> then attach; or use Java debug for JDWP",
        "android": {"adb": "adb", "package": "com.example.app"},
    },
    {
        "id": "ios",
        "label": "iOS (lldb)",
        "family": "mobile",
        "type": "custom",
        "request": "attach",
        "debugAdapter": ["lldb-dap"],
        "ios": {"device": "iphone", "bundleId": "com.example.app"},
        "hint": "Requires Xcode / ios-deploy / remote lldb",
    },
    {
        "id": "fpga-softcore",
        "label": "FPGA soft-core (GDB remote)",
        "family": "fpga",
        "type": "custom",
        "request": "attach",
        "debugAdapter": ["gdb-multiarch", "--interpreter=mi"],
        "miDebuggerServerAddress": "localhost:3333",
        "device": "fpga",
    },
]


def launch_presets_for_catalog() -> list[dict[str, Any]]:
    """Flatten language + hardware into launch.json-ready configurations."""
    out: list[dict[str, Any]] = []
    for lang in LANGUAGE_PRESETS:
        if lang["id"] in {"python", "node"}:
            continue  # already in default_document
        cfg: dict[str, Any] = {
            "name": f"{lang['label']}: current file",
            "type": lang.get("type") or "custom",
            "request": "launch",
            "program": "${file}",
            "cwd": "${workspaceFolder}",
            "language": lang["id"],
        }
        if lang.get("adapter") and lang.get("type") == "custom":
            cfg["debugAdapter"] = lang["adapter"]
        if lang.get("runtimeArgs"):
            cfg["runtimeArgs"] = lang["runtimeArgs"]
        if lang.get("hint"):
            cfg["zintriqHint"] = lang["hint"]
        out.append(cfg)
    for hw in HARDWARE_PRESETS:
        cfg = {
            "name": hw["label"],
            "type": hw.get("type") or "custom",
            "request": hw.get("request") or "attach",
            "cwd": "${workspaceFolder}",
            "hardware": hw["id"],
            "device": hw.get("device"),
            "family": hw.get("family"),
        }
        if hw.get("debugAdapter"):
            cfg["debugAdapter"] = hw["debugAdapter"]
        if hw.get("program"):
            cfg["program"] = hw["program"]
        if hw.get("miDebuggerServerAddress"):
            cfg["miDebuggerServerAddress"] = hw["miDebuggerServerAddress"]
        if hw.get("env"):
            cfg["env"] = hw["env"]
        if hw.get("preLaunchTask"):
            cfg["preLaunchTask"] = hw["preLaunchTask"]
        if hw.get("hint"):
            cfg["zintriqHint"] = hw["hint"]
        for key in ("android", "ios", "configFiles"):
            if hw.get(key):
                cfg[key] = hw[key]
        out.append(cfg)
    return out


def detect_language(path: str) -> dict[str, Any] | None:
    ext = Path(path or "").suffix.lower()
    for lang in LANGUAGE_PRESETS:
        if ext in lang.get("extensions") or []:
            return dict(lang)
    return None


def adapter_availability() -> dict[str, Any]:
    langs = []
    for lang in LANGUAGE_PRESETS:
        tools = lang.get("which") or []
        found = [t for t in tools if shutil.which(str(t))]
        langs.append(
            {
                "id": lang["id"],
                "label": lang["label"],
                "available": bool(found) or lang.get("adapter") == "cdp",
                "found": found,
            }
        )
    hw = []
    for h in HARDWARE_PRESETS:
        da = h.get("debugAdapter") or []
        exe = da[0] if isinstance(da, list) and da else None
        hw.append(
            {
                "id": h["id"],
                "label": h["label"],
                "family": h.get("family"),
                "available": bool(exe and shutil.which(str(exe))),
                "tool": exe,
            }
        )
    return {"ok": True, "languages": langs, "hardware": hw}


# ---------------------------------------------------------------------------
# Extensions: .zintriq/extensions/<id>/package.json
# ---------------------------------------------------------------------------

def extensions_root(workspace: Path) -> Path:
    return workspace.resolve() / ".zintriq" / "extensions"


def list_extensions(workspace: Path) -> dict[str, Any]:
    root = extensions_root(workspace)
    items = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            pkg = d / "package.json"
            if not pkg.is_file():
                continue
            try:
                raw = json.loads(pkg.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            contributes = raw.get("contributes") if isinstance(raw, dict) else {}
            items.append(
                {
                    "id": d.name,
                    "name": raw.get("displayName") or raw.get("name") or d.name,
                    "version": raw.get("version") or "0.0.0",
                    "enabled": raw.get("enabled", True) is not False,
                    "debugAdapters": (contributes or {}).get("debugAdapters") or [],
                    "launch": (contributes or {}).get("launch") or [],
                    "path": f".zintriq/extensions/{d.name}",
                }
            )
    return {"ok": True, "extensions": items, "root": ".zintriq/extensions"}


def install_extension_stub(workspace: Path, ext_id: str, *, label: str = "") -> dict[str, Any]:
    """Create a minimal debug extension package (user can fill adapter paths)."""
    eid = (ext_id or "").strip().replace("..", "")
    if not eid or "/" in eid or "\\" in eid:
        raise ValueError("invalid extension id")
    d = extensions_root(workspace) / eid
    d.mkdir(parents=True, exist_ok=True)
    pkg = {
        "name": eid,
        "displayName": label or eid,
        "version": "0.1.0",
        "engines": {"zintriq": ">=0.1"},
        "contributes": {
            "debugAdapters": [
                {
                    "type": eid,
                    "label": label or eid,
                    "program": "${extensionPath}/adapter.js",
                    "runtime": "node",
                }
            ],
            "launch": [
                {
                    "name": f"{label or eid}: launch",
                    "type": eid,
                    "request": "launch",
                    "program": "${file}",
                }
            ],
        },
    }
    (d / "package.json").write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
    (d / "adapter.js").write_text(
        "// Zintriq debug adapter stub — replace with real DAP stdio bridge\n"
        "process.stderr.write('[zintriq-ext] adapter stub\\n');\n",
        encoding="utf-8",
    )
    (d / "README.md").write_text(
        f"# {label or eid}\n\nContributes debug adapter type `{eid}`.\n",
        encoding="utf-8",
    )
    return {"ok": True, "id": eid, "path": f".zintriq/extensions/{eid}"}


def resolve_extension_adapters(workspace: Path) -> list[dict[str, Any]]:
    """Merge contributed adapters from enabled extensions."""
    adapters = []
    for ext in list_extensions(workspace).get("extensions") or []:
        if not ext.get("enabled"):
            continue
        for a in ext.get("debugAdapters") or []:
            if isinstance(a, dict):
                adapters.append({**a, "extensionId": ext["id"], "extensionPath": ext["path"]})
    return adapters


def extension_launch_configs(workspace: Path) -> list[dict[str, Any]]:
    configs = []
    for ext in list_extensions(workspace).get("extensions") or []:
        if not ext.get("enabled"):
            continue
        for c in ext.get("launch") or []:
            if isinstance(c, dict):
                configs.append({**c, "extensionId": ext["id"]})
    return configs


def catalog_summary(workspace: Path) -> dict[str, Any]:
    avail = adapter_availability()
    exts = list_extensions(workspace)
    return {
        "ok": True,
        "languages": avail["languages"],
        "hardware": avail["hardware"],
        "extensions": exts["extensions"],
        "contributedAdapters": resolve_extension_adapters(workspace),
        "presets": launch_presets_for_catalog(),
    }
