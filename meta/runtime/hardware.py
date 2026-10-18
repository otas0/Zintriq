"""Hardware module runtime: pair, ESPHome YAML, signed OTA.

Three first-party modules: climate (temp/humidity), relay, presence.
Compile stays host-independent; flash is a local plan under ZINTRIQ_DATA_DIR.
"""

from __future__ import annotations

import glob
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meta.description.composite import StructDesc
from meta.description.types import AtomDesc, Desc
from meta.instantiation.errors import InstantiationError

MODULES = ("climate", "relay", "presence")

_SENSE_TO_MODULE = {
    "climate": "climate",
    "temp": "climate",
    "temperature": "climate",
    "humidity": "climate",
    "dht22": "climate",
    "relay": "relay",
    "switch": "relay",
    "presence": "presence",
    "pir": "presence",
    "mmwave": "presence",
}


@dataclass(frozen=True)
class Device:
    id: str
    module: str
    port: str
    token: str
    paired_at: float

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "module": self.module,
            "paired_at": self.paired_at,
            "port": self.port,
            "token": self.token,
        }


def _atom(fields: dict, name: str) -> str:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value:
        return str(node.value if node.value is not None else "")
    return ""


def module_of(desc: Desc) -> str:
    if not isinstance(desc, StructDesc):
        raise InstantiationError("hardware module must be a struct")
    fields = dict(desc.fields)
    hint = (_atom(fields, "sense") or _atom(fields, "act") or _atom(fields, "module")).strip().lower()
    if hint in MODULES:
        return hint
    mapped = _SENSE_TO_MODULE.get(hint)
    if mapped:
        return mapped
    return "presence"


def esphome_yaml(desc: Desc, device: Device) -> str:
    module = device.module
    title = "Zintriq"
    if isinstance(desc, StructDesc):
        label = _atom(dict(desc.fields), "title")
        if label:
            title = label
    name = f"zintriq-{device.id}"
    lines = [
        "esphome:",
        f"  name: {name}",
        f"  friendly_name: {title}",
        "esp32:",
        "  board: esp32dev",
        "  framework:",
        "    type: arduino",
        "logger:",
        "api:",
        "  encryption:",
        f"    key: \"{device.token}\"",
        "ota:",
        "  platform: esphome",
        f"  password: \"{device.token[:16]}\"",
        "wifi:",
        "  ssid: !secret wifi_ssid",
        "  password: !secret wifi_password",
    ]
    if module == "climate":
        lines += [
            "sensor:",
            "  - platform: dht",
            "    pin: GPIO4",
            "    temperature:",
            "      name: Temperature",
            "    humidity:",
            "      name: Humidity",
            "    model: DHT22",
        ]
    elif module == "relay":
        lines += [
            "switch:",
            "  - platform: gpio",
            "    pin: GPIO5",
            "    id: relay_1",
            "    name: Relay",
        ]
    else:
        lines += [
            "binary_sensor:",
            "  - platform: gpio",
            "    pin:",
            "      number: GPIO16",
            "      mode: INPUT_PULLUP",
            "    name: Presence",
            "    device_class: occupancy",
        ]
    return "\n".join(lines) + "\n"


def ota_key(data_root: Path) -> bytes:
    path = Path(data_root) / "hardware" / "ota.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return path.read_bytes()
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def sign_ota(payload: bytes, data_root: Path) -> dict[str, str]:
    key = ota_key(data_root)
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return {
        "alg": "hmac-sha256",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "signature": digest,
    }


def verify_ota(payload: bytes, signature: str, data_root: Path) -> bool:
    expected = sign_ota(payload, data_root)["signature"]
    return hmac.compare_digest(expected, str(signature or ""))


def flash_plan(device: Device, yaml_text: str, *, data_root: Path) -> dict[str, Any]:
    hw = Path(data_root) / "hardware" / device.id
    hw.mkdir(parents=True, exist_ok=True)
    yaml_path = hw / "module.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    signed = sign_ota(yaml_text.encode("utf-8"), data_root)
    (hw / "ota.json").write_text(json.dumps(signed, indent=2), encoding="utf-8")
    esphome = _esphome_bin() or "esphome"
    return {
        "commands": [
            [esphome, "compile", str(yaml_path)],
            [esphome, "upload", str(yaml_path), "--device", device.port],
        ],
        "module": device.module,
        "ota": signed,
        "port": device.port,
        "yaml_path": str(yaml_path),
    }


def pair(desc: Desc, *, port: str = "usb", data_root: Path | None = None) -> Device:
    module = module_of(desc)
    device = Device(
        id=secrets.token_hex(4),
        module=module,
        port=str(port or "usb").strip() or "usb",
        token=secrets.token_urlsafe(24),
        paired_at=time.time(),
    )
    if data_root is not None:
        folder = Path(data_root) / "hardware" / device.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "device.json").write_text(json.dumps(device.to_data()), encoding="utf-8")
        yaml_text = esphome_yaml(desc, device)
        (folder / "module.yaml").write_text(yaml_text, encoding="utf-8")
    return device


def persist_device_artifact(artifact_body: dict[str, Any], *, data_root: Path) -> Path:
    device = artifact_body.get("device") or {}
    ident = str(device.get("id") or "").strip()
    if not ident:
        raise InstantiationError("device artifact missing id")
    folder = Path(data_root) / "hardware" / ident
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "device.json").write_text(json.dumps(device), encoding="utf-8")
    yaml_text = str(artifact_body.get("esphome") or "")
    (folder / "module.yaml").write_text(yaml_text, encoding="utf-8")
    return folder


def list_devices(data_root: Path) -> list[dict[str, Any]]:
    root = Path(data_root) / "hardware"
    if not root.is_dir():
        return []
    rows = []
    for child in sorted(root.iterdir()):
        path = child / "device.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("id"):
            rows.append(data)
    return rows


def device_artifact_body(desc: Desc, slug: str | None = None) -> dict[str, Any]:
    from meta.description import to_json
    from meta.runtime.kernels import kernel_spec

    compiled = kernel_spec(desc)
    kind = str(compiled.get("kind") or "")
    if kind in {"print3d.job", "cnc.job", "robotics.cell"}:
        return {
            "compiled": compiled,
            "description": json.loads(to_json(desc)),
            "slug": slug or "",
            "target": "device",
        }
    device = pair(desc, port="usb")
    yaml_text = esphome_yaml(desc, device)
    return {
        "compiled": compiled,
        "description": json.loads(to_json(desc)),
        "device": device.to_data(),
        "esphome": yaml_text,
        "module": device.module,
        "slug": slug or "",
    }


_PORT_RE = re.compile(r"^(COM\d{1,3}|/dev/[A-Za-z0-9._-]+|[A-Za-z0-9._:-]+)$")
_JOBS: dict[str, dict[str, Any]] = {}
_JOB_LOCK = threading.Lock()


def list_serial_ports() -> list[dict[str, str]]:
    fake = (os.environ.get("ZINTRIQ_FAKE_SERIAL") or "").strip()
    if fake:
        return [{"label": "fake", "path": fake}]
    found: list[dict[str, str]] = []
    if os.name == "nt":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
            index = 0
            while True:
                try:
                    _name, value, _typ = winreg.EnumValue(key, index)
                except OSError:
                    break
                path = str(value)
                found.append({"label": path, "path": path})
                index += 1
        except OSError:
            pass
        return found

    patterns = ["/dev/cu.usb*", "/dev/cu.wchusbserial*", "/dev/cu.SLAB*", "/dev/cu.usbserial*", "/dev/ttyUSB*", "/dev/ttyACM*"]
    seen = set()
    for pattern in patterns:
        for path in glob.glob(pattern):
            if path in seen:
                continue
            seen.add(path)
            found.append({"label": os.path.basename(path), "path": path})
    return found


def validate_port(port: str) -> str:
    value = str(port or "").strip()
    if not value or not _PORT_RE.fullmatch(value):
        raise InstantiationError("serial port is invalid")
    allowed = {item["path"] for item in list_serial_ports()}
    if allowed and value not in allowed:
        raise InstantiationError("serial port is not connected")
    return value


def wifi_store_path(data_root: Path) -> Path:
    return Path(data_root) / "hardware" / "wifi.json"


def load_wifi(data_root: Path) -> dict[str, str]:
    path = wifi_store_path(data_root)
    if not path.is_file():
        return {"password": "", "ssid": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"password": "", "ssid": ""}
    if not isinstance(data, dict):
        return {"password": "", "ssid": ""}
    return {
        "password": str(data.get("password") or ""),
        "ssid": str(data.get("ssid") or ""),
    }


def save_wifi(data_root: Path, *, ssid: str, password: str | None) -> dict[str, str]:
    current = load_wifi(data_root)
    next_ssid = str(ssid or "").strip()
    if password is None:
        next_password = current.get("password") or ""
    else:
        next_password = str(password)
    path = wifi_store_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"password": next_password, "ssid": next_ssid}
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return payload


def wifi_public(data_root: Path) -> dict[str, Any]:
    row = load_wifi(data_root)
    return {"has_password": bool(row.get("password")), "ssid": row.get("ssid") or ""}


def write_secrets_yaml(yaml_dir: Path, *, ssid: str, password: str) -> Path:
    folder = Path(yaml_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "secrets.yaml"
    text = "wifi_ssid: {ssid}\nwifi_password: {password}\n".format(
        ssid=json.dumps(str(ssid or ""), ensure_ascii=False),
        password=json.dumps(str(password or ""), ensure_ascii=False),
    )
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _esphome_bin() -> str:
    return (os.environ.get("ESPHOME_BIN") or "").strip()


def esphome_venv_dir(data_root: Path) -> Path:
    return Path(data_root) / "tools" / "esphome"


def esphome_venv_executable(data_root: Path) -> Path:
    folder = esphome_venv_dir(data_root)
    if os.name == "nt":
        return folder / "Scripts" / "esphome.exe"
    return folder / "bin" / "esphome"


def resolve_esphome_bin(data_root: Path) -> str:
    import shutil

    pinned = _esphome_bin()
    if pinned:
        return pinned
    found = shutil.which("esphome")
    if found:
        return found
    local = esphome_venv_executable(data_root)
    if local.is_file():
        return str(local)
    if (os.environ.get("ZINTRIQ_SKIP_ESPHOME_INSTALL") or "").strip():
        raise InstantiationError("ESPHome is not installed")
    _install_esphome(data_root)
    if not local.is_file():
        raise InstantiationError("ESPHome install did not produce a binary")
    return str(local)


def _install_esphome(data_root: Path) -> None:
    import subprocess
    import sys

    venv = esphome_venv_dir(data_root)
    venv.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    subprocess.run([py, "-m", "venv", str(venv)], check=True, timeout=120)
    if os.name == "nt":
        pip = venv / "Scripts" / "pip.exe"
    else:
        pip = venv / "bin" / "pip"
    subprocess.run(
        [str(pip), "install", "--upgrade", "pip", "esphome"],
        check=True,
        timeout=600,
    )


def _append_log(job: dict[str, Any], line: str) -> None:
    job["log"] = (str(job.get("log") or "") + line + "\n")[-20000:]


def job_status(job_id: str) -> dict[str, Any] | None:
    with _JOB_LOCK:
        row = _JOBS.get(str(job_id or "").strip())
        return dict(row) if row else None


def start_flash(
    *,
    port: str,
    yaml_path: str,
    data_root: Path,
    ssid: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    import subprocess
    import uuid

    clean_port = validate_port(port)
    yaml_file = Path(yaml_path)
    if not yaml_file.is_file():
        raise InstantiationError("firmware yaml missing")
    try:
        yaml_file.resolve().relative_to(Path(data_root).resolve())
    except ValueError as exc:
        raise InstantiationError("firmware yaml must stay in the data directory") from exc
    if ssid is not None:
        wifi = save_wifi(data_root, ssid=ssid, password=password)
    else:
        wifi = load_wifi(data_root)
    if not str(wifi.get("ssid") or "").strip():
        raise InstantiationError("Wi-Fi SSID is required")
    write_secrets_yaml(yaml_file.parent, ssid=str(wifi.get("ssid") or ""), password=str(wifi.get("password") or ""))
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "log": "",
        "port": clean_port,
        "status": "queued",
        "yaml_path": str(yaml_file),
    }
    with _JOB_LOCK:
        _JOBS[job_id] = job
    try:
        bin_path = resolve_esphome_bin(data_root)
    except InstantiationError as exc:
        job["status"] = "error"
        _append_log(job, str(exc))
        return dict(job)
    _append_log(job, "using " + bin_path)

    def run() -> None:
        with _JOB_LOCK:
            job["status"] = "running"
        commands = [
            [bin_path, "compile", str(yaml_file)],
            [bin_path, "upload", str(yaml_file), "--device", clean_port],
        ]
        try:
            for argv in commands:
                _append_log(job, "$ " + " ".join(argv))
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
                if proc.stdout:
                    _append_log(job, proc.stdout)
                if proc.stderr:
                    _append_log(job, proc.stderr)
                if proc.returncode != 0:
                    job["status"] = "error"
                    _append_log(job, "exit " + str(proc.returncode))
                    return
            job["status"] = "ok"
            _append_log(job, "flash complete")
        except subprocess.TimeoutExpired:
            job["status"] = "error"
            _append_log(job, "timed out")
        except OSError as exc:
            job["status"] = "error"
            _append_log(job, str(exc))

    threading.Thread(target=run, name="zintriq-esphome", daemon=True).start()
    return dict(job)
