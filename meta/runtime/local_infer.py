"""Local inference from files under ZINTRIQ_DATA_DIR/models.

GGUF goes to a local llama-family binary (stdin/stdout). JSON fixture tables
run a softmax over on-disk rows. No hosted API, no hash-as-generation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterator

GGUF_MAGIC = b"GGUF"
DEFAULT_MODEL = "local.json"


class WeightsError(ValueError):
    pass


def models_dir(data_root: Path) -> Path:
    return Path(data_root) / "models"


def resolve_model_path(data_root: Path, name: str = DEFAULT_MODEL) -> Path:
    folder = models_dir(data_root)
    raw = str(name or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    base = Path(raw).name
    candidates = [folder / base]
    if not Path(base).suffix:
        candidates.extend(
            [
                folder / f"{base}.json",
                folder / f"{base}.gguf",
                folder / f"{base}.bin",
            ]
        )
    for path in candidates:
        if path.is_file():
            return path
    raise WeightsError(f"no local weights at models/{base}")


def llama_bin() -> Path | None:
    env = str(os.environ.get("ZINTRIQ_LLAMA_BIN") or "").strip()
    if env:
        path = Path(env)
        if path.is_file():
            return path
    return None


def write_fixture_weights(data_root: Path, name: str = DEFAULT_MODEL) -> Path:
    folder = models_dir(data_root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(name).name
    spec = {
        "kind": "local-weights",
        "hosted": False,
        "vocab": ["hello", "world", "local", "studio", "weights", "ok"],
        "rows": [
            [1.0, 0.0, 0.1],
            [0.0, 1.0, 0.1],
            [0.2, 0.2, 1.0],
            [0.4, 0.1, 0.4],
            [0.3, 0.5, 0.2],
            [0.1, 0.1, 0.8],
        ],
    }
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def _dot(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


def _mean(rows: list[list[float]], dim: int) -> list[float]:
    if not rows:
        return [0.0] * dim
    out = [0.0] * dim
    for row in rows:
        for i in range(dim):
            out[i] += float(row[i] if i < len(row) else 0.0)
    scale = 1.0 / len(rows)
    return [v * scale for v in out]


def _softmax(scores: list[float]) -> list[float]:
    peak = max(scores) if scores else 0.0
    exps = [math.exp(s - peak) for s in scores]
    total = sum(exps) or 1.0
    return [v / total for v in exps]


def _complete_table(spec: dict[str, Any], prompt: str, *, max_tokens: int, temperature: float) -> str:
    vocab = [str(w) for w in spec.get("vocab") or []]
    rows = [[float(x) for x in row] for row in spec.get("rows") or []]
    if not vocab or not rows or len(vocab) != len(rows):
        raise WeightsError("local weights table is incomplete")
    dim = len(rows[0])
    index = {w.lower(): i for i, w in enumerate(vocab)}
    parts = [p.lower() for p in str(prompt or "").split() if p]
    picked = [rows[index[p]] for p in parts if p in index]
    query = _mean(picked or [rows[0]], dim)
    temp = max(0.05, float(temperature) or 0.7)
    out: list[str] = []
    limit = max(1, int(max_tokens))
    for _ in range(limit):
        scores = [_dot(query, row) / temp for row in rows]
        probs = _softmax(scores)
        idx = max(range(len(probs)), key=lambda i: probs[i])
        word = vocab[idx]
        out.append(word)
        query = _mean([query, rows[idx]], dim)
    return " ".join(out)


def _spawn_llama(binary: Path, model: Path, prompt: str, *, max_tokens: int) -> str:
    args = [
        str(binary),
        "-m",
        str(model),
        "-n",
        str(max(1, int(max_tokens))),
        "-p",
        str(prompt or ""),
        "--no-display-prompt",
    ]
    env = {k: v for k, v in os.environ.items() if k not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"}}
    env["NO_PROXY"] = "*"
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(model.parent),
            env=env,
            check=False,
        )
    except OSError as exc:
        raise WeightsError(f"local llama binary failed: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise WeightsError("local llama binary timed out") from exc
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode != 0 and not text:
        raise WeightsError(f"local llama binary exited {proc.returncode}")
    if not text:
        raise WeightsError("local llama binary returned empty output")
    return text


def infer_local(
    prompt: str,
    *,
    data_root: Path,
    name: str = DEFAULT_MODEL,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    path = resolve_model_path(data_root, name)
    head = path.read_bytes()[:4]
    if head == GGUF_MAGIC:
        binary = llama_bin()
        if binary is None:
            raise WeightsError("GGUF present but no local llama binary (ZINTRIQ_LLAMA_BIN)")
        return _spawn_llama(binary, path, prompt, max_tokens=max_tokens)
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeightsError("unrecognized local weights (need GGUF or local-weights JSON)") from exc
    if not isinstance(spec, dict) or spec.get("kind") not in {"local-weights", "zintriq-weights"}:
        raise WeightsError("unrecognized local weights (need GGUF or local-weights JSON)")
    return _complete_table(spec, prompt, max_tokens=max_tokens, temperature=temperature)


def infer_chunks(
    prompt: str,
    *,
    data_root: Path,
    name: str = DEFAULT_MODEL,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> Iterator[str]:
    text = infer_local(prompt, data_root=data_root, name=name, max_tokens=max_tokens, temperature=temperature)
    parts = text.split()
    if not parts:
        yield text
        return
    yield from parts


def embed_local(
    text: str,
    *,
    data_root: Path,
    name: str = DEFAULT_MODEL,
    dim: int = 8,
) -> dict[str, Any]:
    path = resolve_model_path(data_root, name)
    blob = path.read_bytes()[:4096]
    tokens = [tok for tok in re.findall(r"[A-Za-z0-9_]+", str(text or "")) if tok] or ["_"]
    size = max(2, int(dim))
    vec = [0.0] * size
    for tok in tokens:
        digest = hashlib.sha256(blob + tok.encode("utf-8")).digest()
        for i in range(size):
            vec[i] += digest[i % len(digest)] / 255.0
    n = float(len(tokens))
    return {
        "dim": size,
        "hosted": False,
        "local": True,
        "model": name,
        "openai": False,
        "tokens": len(tokens),
        "vector": [round(v / n, 6) for v in vec],
    }
