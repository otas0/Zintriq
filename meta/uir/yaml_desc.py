"""Restricted YAML for Desc JSON objects (second code language)."""

from __future__ import annotations

import json
from typing import Any

from meta.uir.errors import UIRError


def dump_yaml(data: Any, *, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return "{}" if indent == 0 else pad + "{}"
        lines = []
        for key, value in data.items():
            if isinstance(value, dict) and value:
                lines.append(f"{pad}{key}:")
                lines.append(dump_yaml(value, indent=indent + 1))
            elif isinstance(value, list) and value:
                lines.append(f"{pad}{key}:")
                lines.append(dump_yaml(value, indent=indent + 1))
            else:
                lines.append(f"{pad}{key}: {_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return "[]" if indent == 0 else pad + "[]"
        lines = []
        for item in data:
            if isinstance(item, (dict, list)) and item:
                nested = dump_yaml(item, indent=indent + 1)
                first, _, rest = nested.partition("\n")
                lines.append(f"{pad}- {first.lstrip()}")
                if rest:
                    lines.append(rest)
            else:
                lines.append(f"{pad}- {_scalar(item)}")
        return "\n".join(lines)
    return _scalar(data)


def _scalar(data: Any) -> str:
    if data is None:
        return "null"
    if isinstance(data, bool):
        return "true" if data else "false"
    if isinstance(data, int) and not isinstance(data, bool):
        return str(data)
    if isinstance(data, float):
        return repr(data)
    if isinstance(data, str):
        if data == "" or any(ch in data for ch in ":#\n\"'") or data.strip() != data:
            return json.dumps(data, ensure_ascii=False)
        return data
    if isinstance(data, (dict, list)):
        return dump_yaml(data)
    return json.dumps(data, ensure_ascii=False)


def load_yaml(text: str) -> Any:
    raw = str(text or "")
    stripped = raw.strip()
    if not stripped:
        raise UIRError("empty yaml")
    if stripped[0] in "{[":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise UIRError(f"invalid json: {exc}") from exc
    lines = raw.replace("\t", "  ").splitlines()
    data, _next = _parse_block(lines, 0, 0)
    return data


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return {}, index
    if _indent_of(lines[index]) < indent:
        return {}, index
    if lines[index].lstrip().startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_map(lines, index, indent)


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_map(lines: list[str], index: int, indent: int) -> tuple[dict[str, Any], int]:
    out: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        current = _indent_of(line)
        if current < indent:
            break
        if current > indent:
            raise UIRError("invalid yaml indent")
        if line.lstrip().startswith("- "):
            break
        stripped = line.strip()
        if ":" not in stripped:
            raise UIRError(f"invalid yaml line: {stripped!r}")
        key, rest = stripped.split(":", 1)
        rest = rest.strip()
        index += 1
        if rest == "":
            value, index = _parse_block(lines, index, indent + 2)
            out[key] = value
        else:
            out[key] = _parse_scalar(rest)
    return out, index


def _parse_list(lines: list[str], index: int, indent: int) -> tuple[list[Any], int]:
    out: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        current = _indent_of(line)
        if current < indent:
            break
        if not line.lstrip().startswith("- "):
            break
        rest = line.lstrip()[2:]
        index += 1
        if rest.strip() == "":
            value, index = _parse_block(lines, index, current + 2)
            out.append(value)
        else:
            out.append(_parse_scalar(rest.strip()))
    return out, index


def _parse_scalar(text: str) -> Any:
    raw = text.strip()
    if raw in {"null", "~", "{}"}:
        return {} if raw == "{}" else None
    if raw == "[]":
        return []
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith('"'):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip('"')
    try:
        if "." in raw or "e" in raw.lower():
            return float(raw)
        return int(raw)
    except ValueError:
        return raw
