"""Whitelisted local AI tools. Not an OpenAI platform."""

from __future__ import annotations

from typing import Any

from meta.description import from_json, to_json
from meta.instantiation.errors import InstantiationError
from meta.instantiation.system import add_system_part
from meta.runtime.kernels import WeightsError, complete_session
from plugin_catalog import PluginError, submit

ALLOWED_TOOLS = frozenset({"add_part", "submit_plugin", "explain"})


def run_tool(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    code: str = "",
    data_root=None,
    model: str = "local.json",
) -> dict[str, Any]:
    tool = str(name or "").strip()
    if tool not in ALLOWED_TOOLS:
        return {"error": "unknown tool", "hosted": False, "ok": False, "tool": tool}
    body = args if isinstance(args, dict) else {}
    if tool == "explain":
        if data_root is None:
            return {"error": "no local weights", "hosted": False, "ok": False, "tool": tool}
        session = complete_session(
            prompt=str(body.get("error") or body.get("prompt") or code or "explain"),
            data_root=data_root,
            name=model,
            max_tokens=int(body.get("max_tokens") or 64),
            system="Explain a Zintriq instantiate error. Local only.",
        )
        session["ok"] = True
        session["tool"] = tool
        return session
    if tool == "submit_plugin":
        try:
            pack = submit(
                {
                    "id": str(body.get("id") or "community-draft"),
                    "name": str(body.get("name") or "Draft pack"),
                    "form": str(body.get("form") or "view"),
                    "summary": str(body.get("summary") or "assistant draft"),
                }
            )
        except PluginError as exc:
            return {"error": str(exc), "hosted": False, "ok": False, "tool": tool}
        return {"hosted": False, "ok": True, "pack": pack, "status": pack.get("status"), "tool": tool}
    if tool == "add_part":
        try:
            desc = from_json(code)
            updated = add_system_part(
                desc,
                key=str(body.get("key") or "") or None,
                title=str(body.get("title") or ""),
                part_kind=str(body.get("kind") or "scene"),
            )
        except (InstantiationError, ValueError, TypeError) as exc:
            return {"error": str(exc), "hosted": False, "ok": False, "tool": tool}
        return {"code": to_json(updated), "hosted": False, "ok": True, "tool": tool}
    return {"error": "unknown tool", "hosted": False, "ok": False, "tool": tool}
