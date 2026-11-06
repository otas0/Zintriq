"""Isolated AI worker. No disk writes — stdout JSON only.

Env (optional, for real models):
  ZINTRIQ_AI_BASE_URL  default https://api.openai.com/v1
  ZINTRIQ_AI_API_KEY   required for remote
  ZINTRIQ_AI_MODEL     default gpt-4o-mini

Without a key → deterministic local stub (offline).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _stub(prompt: str, path: str, text: str) -> dict:
    banner = f"# ai: {prompt[:120].replace(chr(10), ' ')}\n"
    if text.startswith("# ai:"):
        after = text
    elif text:
        after = banner + text
    else:
        after = banner + f"# path: {path}\n"
    return {
        "ok": True,
        "after": after,
        "note": "local stub (no API key)",
        "provider": "stub",
    }


def _openai_chat(prompt: str, path: str, text: str) -> dict:
    key = (os.environ.get("ZINTRIQ_AI_API_KEY") or "").strip()
    if not key:
        return _stub(prompt, path, text)
    base = (os.environ.get("ZINTRIQ_AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = (os.environ.get("ZINTRIQ_AI_MODEL") or "gpt-4o-mini").strip()
    system = (
        "You are a coding assistant inside Zintriq Editor. "
        "Return ONLY the full revised file contents. No markdown fences, no explanation."
    )
    user = (
        f"File: {path}\n\nUser request:\n{prompt}\n\nCurrent file:\n```\n{text}\n```\n"
        "Respond with the complete new file body only."
    )
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    try:
        after = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "error": "unexpected model response"}
    after = _strip_fences(str(after))
    if not after:
        return {"ok": False, "error": "empty model output"}
    return {
        "ok": True,
        "after": after,
        "note": f"{model} via {base}",
        "provider": "openai-compatible",
    }


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines)
    return t


def run(payload: dict) -> dict:
    prompt = str(payload.get("prompt") or "").strip()
    path = str(payload.get("path") or "untitled.txt")
    text = str(payload.get("text") or "")
    if not prompt:
        return {"ok": False, "error": "empty prompt"}
    allow_net = bool(payload.get("allow_network"))
    if allow_net and (os.environ.get("ZINTRIQ_AI_API_KEY") or "").strip():
        return _openai_chat(prompt, path, text)
    return _stub(prompt, path, text)


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"bad json: {exc}"}))
        return 1
    result = run(payload if isinstance(payload, dict) else {})
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
