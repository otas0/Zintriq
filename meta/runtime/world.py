"""Playable local worlds compiled from domain descriptions.

These are not Unity, Unreal, Roblox, Blender, Stripe, YouTube, Discord, or
hosted LLM products. They are the same meta path: describe → simulate →
instantiate a runtime the author can run on this machine and keep extending.
"""

from __future__ import annotations

import html
import json
from typing import Any

from meta.description.composite import SequenceDesc, StructDesc
from meta.description.types import AtomDesc, Desc

from meta.runtime.kernels import KERNEL_KINDS, kernel_spec

WORLD_KINDS = frozenset(
    {
        "ai",
        "animation",
        "audio",
        "bitmap",
        "cad.solid",
        "chip",
        "circuit",
        "commerce.checkout",
        "data.table",
        "document",
        "font",
        "level",
        "logic",
        "map",
        "material",
        "media.channel",
        "model3d",
        "node.graph",
        "particle",
        "quantum",
        "scene",
        "shader",
        "social.channel",
        "spreadsheet",
        "terrain",
        "text",
        "vector",
        "video",
        "world.place",
    }
    | KERNEL_KINDS
)

FAMILY = {
    "ai": "llm",
    "animation": "media",
    "audio": "media",
    "bitmap": "media",
    "cad.solid": "cad",
    "chip": "cad",
    "circuit": "cad",
    "commerce.checkout": "commerce",
    "data.table": "commerce",
    "document": "software",
    "font": "media",
    "level": "game",
    "logic": "game",
    "world.place": "game",
    "map": "cad",
    "material": "cad",
    "media.channel": "media",
    "model3d": "cad",
    "node.graph": "game",
    "particle": "game",
    "quantum": "cad",
    "scene": "game",
    "shader": "game",
    "social.channel": "social",
    "spreadsheet": "commerce",
    "terrain": "game",
    "text": "software",
    "vector": "cad",
    "video": "media",
    "physics.body": "game",
    "skeleton.rig": "game",
    "film.cut": "media",
    "cad.brep": "cad",
    "commerce.settle": "commerce",
    "social.federate": "social",
    "llm.weights": "llm",
}


def is_world_kind(kind: str) -> bool:
    return str(kind or "").strip() in WORLD_KINDS


def world_spec(desc: Desc) -> dict[str, Any]:
    kind = _kind(desc)
    fields = dict(desc.fields) if isinstance(desc, StructDesc) else {}
    spec: dict[str, Any] = {
        "family": FAMILY.get(kind, "software"),
        "kind": kind,
        "title": _atom(fields, "title") or kind or "World",
    }
    if kind in KERNEL_KINDS:
        merged = kernel_spec(desc)
        if isinstance(merged, dict):
            spec.update(merged)
        spec["family"] = FAMILY.get(kind, spec.get("family") or "software")
        spec["kind"] = kind
        spec["title"] = _atom(fields, "title") or spec.get("title") or kind
    if kind == "scene":
        cam = _struct(fields, "camera")
        frustum = spec.get("frustum") if isinstance(spec.get("frustum"), dict) else {}
        spec["camera"] = {
            **frustum,
            "x": _num(cam, "x", frustum.get("x") or 0),
            "y": _num(cam, "y", frustum.get("y") or 0),
            "z": _num(cam, "z", frustum.get("z") or 8),
        }
        spec["mesh"] = _atom(fields, "mesh") or spec.get("mesh") or "cube"
    elif kind == "level":
        spawn = _struct(fields, "spawn")
        spec["room"] = _atom(fields, "room") or "start"
        spec["spawn"] = {"x": _num(spawn, "x", 0), "y": _num(spawn, "y", 0)}
    elif kind == "world.place":
        spec.update(place_spec(desc))
    elif kind in {"model3d", "cad.solid"}:
        spec["mesh"] = _atom(fields, "mesh") or "box"
        spec["width"] = _num(fields, "width", 2)
        spec["height"] = _num(fields, "height", 2)
        spec["depth"] = _num(fields, "depth", 2)
        spec["gltf"] = _atom(fields, "gltf")
    elif kind == "material":
        spec["albedo"] = _atom(fields, "albedo") or "#888888"
        spec["metal"] = _num(fields, "metal", 0)
        spec["rough"] = _num(fields, "rough", 0.5)
    elif kind == "animation":
        spec["duration"] = _num(fields, "duration", 1)
        spec["keyframes"] = _rows(fields.get("keyframes"), ("time", "value"))
    elif kind == "video":
        spec["clip"] = _atom(fields, "clip") or "intro"
        spec["frame"] = int(_num(fields, "frame", 0))
    elif kind == "audio":
        spec["hz"] = int(_num(fields, "hz", 440))
        spec["gain"] = _num(fields, "gain", 0.2)
    elif kind == "media.channel":
        spec["name"] = _atom(fields, "name") or spec["title"]
        spec["clips"] = _seq_strings(fields.get("clips")) or ["pilot"]
    elif kind == "social.channel":
        spec["name"] = _atom(fields, "name") or spec["title"]
        spec["messages"] = _seq_strings(fields.get("messages")) or ["channel opened"]
    elif kind == "commerce.checkout":
        spec["currency"] = _atom(fields, "currency") or "usd"
        spec["items"] = _rows(fields.get("items"), ("name", "price"))
        if not spec["items"]:
            spec["items"] = [{"name": "Item", "price": 10}]
    elif kind in {"data.table", "spreadsheet"}:
        spec["rows"] = _table(fields.get("rows"))
    elif kind == "ai":
        spec["model"] = _atom(fields, "model") or "local"
        spec["prompt"] = _atom(fields, "prompt") or "Hello"
    elif kind == "shader":
        spec["glsl"] = _atom(fields, "glsl") or "void main() { gl_FragColor = vec4(1.0); }"
    elif kind == "particle":
        spec["emit"] = int(_num(fields, "emit", 32))
        spec["burst"] = int(_num(fields, "burst", 4))
    elif kind == "terrain":
        spec["height"] = _num(fields, "height", 12)
        spec["noise"] = _num(fields, "noise", 0.4)
    elif kind == "map":
        spec["lat"] = _num(fields, "lat", 0)
        spec["lng"] = _num(fields, "lng", 0)
    elif kind == "quantum":
        spec["qubit"] = int(_num(fields, "qubit", 2))
        spec["hadamard"] = _atom(fields, "hadamard") or "q0"
    elif kind == "vector":
        spec["path"] = _atom(fields, "path") or "M10 10 L80 80"
    elif kind == "text":
        spec["body"] = _seq_strings(fields.get("body"))
    elif kind == "document":
        spec["heading"] = _atom(fields, "heading") or spec["title"]
        spec["paragraph"] = _atom(fields, "paragraph")
    elif kind == "node.graph":
        spec["a"] = _atom(_struct(fields, "a"), "label") or "A"
        spec["b"] = _atom(_struct(fields, "b"), "label") or "B"
    else:
        spec["label"] = _atom(fields, "title") or kind
    return spec


def place_spec(desc: Desc) -> dict[str, Any]:
    fields = dict(desc.fields) if isinstance(desc, StructDesc) else {}
    objects = _rows(fields.get("objects"), ("id", "kind", "x", "y"))
    if not objects:
        objects = [{"id": "origin", "kind": "scene", "x": 0.0, "y": 0.0}]
    logic_child = fields.get("logic")
    scripts: dict[str, Any] = {"kind": "logic", "via": "desc", "roblox": False}
    if isinstance(logic_child, StructDesc):
        scripts = {"kind": "logic", "via": "desc", "roblox": False, "states": kernel_spec(logic_child).get("states")}
    elif _kind(desc) == "logic":
        scripts = kernel_spec(desc)
        scripts["via"] = "desc"
        scripts["roblox"] = False
    return {
        "family": "game",
        "kind": "world.place",
        "objects": objects,
        "place": _atom(fields, "title") or _atom(fields, "place") or "place",
        "roblox": False,
        "scripts": scripts,
        "title": _atom(fields, "title") or "Place",
        "wan": False,
    }


def copy_object(obj: dict[str, Any], *, suffix: str = "-copy") -> dict[str, Any]:
    row = dict(obj or {})
    ident = str(row.get("id") or "obj")
    row["id"] = ident + suffix
    return row


def replicate_objects(local: list[Any] | None, remote: list[Any] | None) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in list(local or []) + list(remote or []):
        if not isinstance(row, dict):
            continue
        ident = str(row.get("id") or "")
        if ident:
            by_id[ident] = dict(row)
    return [by_id[key] for key in sorted(by_id)]


def render_world(desc: Desc) -> str:
    spec = world_spec(desc)
    payload = json.dumps(spec, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    return (
        '<section class="zw" data-world="'
        + html.escape(spec["kind"])
        + '" data-family="'
        + html.escape(spec["family"])
        + '">'
        + '<p class="zw-kicker">'
        + html.escape(spec["family"])
        + " runtime</p>"
        + '<script type="application/json" id="zw-spec">'
        + payload
        + "</script>"
        + "<canvas class='zw-view' id='zw-view' width='640' height='360'></canvas>"
        + "<div id='zw-ui'></div>"
        + "<script>"
        + _WORLD_JS
        + "</script></section>"
    )


def complete_local(prompt: str, model: str = "local") -> str:
    text = " ".join(str(prompt or "").split())
    name = str(model or "local").strip() or "local"
    if not text:
        return name + ": empty prompt"
    words = text.split(" ")
    rest = " ".join(words[:48])
    return name + " · " + rest + (" …" if len(words) > 48 else "")


def seed_desc(kind: str, title: str = "") -> StructDesc:
    from meta.description import atom, sequence, struct

    label = title or kind
    wanted = str(kind or "scene").strip()
    if wanted == "scene":
        return struct(
            camera=struct(
                x=atom("float", value=0, has_value=True),
                y=atom("float", value=0, has_value=True),
                z=atom("float", value=8, has_value=True),
            ),
            kind=atom("string", value="scene", has_value=True),
            mesh=atom("string", value="cube", has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "cad.solid":
        return struct(
            depth=atom("float", value=2, has_value=True),
            height=atom("float", value=2, has_value=True),
            kind=atom("string", value="cad.solid", has_value=True),
            mesh=atom("string", value="box", has_value=True),
            title=atom("string", value=label, has_value=True),
            width=atom("float", value=2, has_value=True),
        )
    if wanted == "commerce.checkout":
        return struct(
            currency=atom("string", value="usd", has_value=True),
            items=sequence(
                struct(
                    name=atom("string", value="Item", has_value=True),
                    price=atom("float", value=10, has_value=True),
                )
            ),
            kind=atom("string", value="commerce.checkout", has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "social.channel":
        return struct(
            kind=atom("string", value="social.channel", has_value=True),
            messages=sequence(atom("string", value="channel opened", has_value=True)),
            name=atom("string", value=label, has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "media.channel":
        return struct(
            clips=sequence(atom("string", value="pilot", has_value=True)),
            kind=atom("string", value="media.channel", has_value=True),
            name=atom("string", value=label, has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "ai":
        return struct(
            kind=atom("string", value="ai", has_value=True),
            model=atom("string", value="local", has_value=True),
            prompt=atom("string", value="Hello", has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "physics.body":
        return struct(
            gravity=atom("float", value=-9.8, has_value=True),
            kind=atom("string", value="physics.body", has_value=True),
            mass=atom("float", value=1, has_value=True),
            title=atom("string", value=label, has_value=True),
            vx=atom("float", value=0, has_value=True),
            vy=atom("float", value=0, has_value=True),
            x=atom("float", value=0, has_value=True),
            y=atom("float", value=10, has_value=True),
        )
    if wanted == "skeleton.rig":
        return struct(
            bones=sequence(
                struct(
                    id=atom("string", value="root", has_value=True),
                    length=atom("float", value=1, has_value=True),
                ),
                struct(
                    id=atom("string", value="arm", has_value=True),
                    length=atom("float", value=1, has_value=True),
                ),
            ),
            kind=atom("string", value="skeleton.rig", has_value=True),
            reach=atom("float", value=1.5, has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "film.cut":
        return struct(
            kind=atom("string", value="film.cut", has_value=True),
            shots=sequence(
                struct(
                    clip=atom("string", value="a", has_value=True),
                    duration=atom("float", value=1, has_value=True),
                ),
                struct(
                    clip=atom("string", value="b", has_value=True),
                    duration=atom("float", value=2, has_value=True),
                ),
            ),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "cad.brep":
        return struct(
            depth=atom("float", value=1, has_value=True),
            height=atom("float", value=1, has_value=True),
            kind=atom("string", value="cad.brep", has_value=True),
            title=atom("string", value=label, has_value=True),
            width=atom("float", value=1, has_value=True),
        )
    if wanted == "commerce.settle":
        return struct(
            amount=atom("float", value=10, has_value=True),
            currency=atom("string", value="usd", has_value=True),
            kind=atom("string", value="commerce.settle", has_value=True),
            ref=atom("string", value="local", has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "social.federate":
        return struct(
            kind=atom("string", value="social.federate", has_value=True),
            messages=sequence(atom("string", value="hello", has_value=True)),
            name=atom("string", value=label, has_value=True),
            remote=sequence(atom("string", value="there", has_value=True)),
            title=atom("string", value=label, has_value=True),
        )
    if wanted == "llm.weights":
        return struct(
            kind=atom("string", value="llm.weights", has_value=True),
            model=atom("string", value="local.bin", has_value=True),
            prompt=atom("string", value="Hello", has_value=True),
            title=atom("string", value=label, has_value=True),
        )
    return struct(
        kind=atom("string", value=wanted, has_value=True),
        title=atom("string", value=label, has_value=True),
    )


def _kind(desc: Desc) -> str:
    if not isinstance(desc, StructDesc):
        return ""
    node = dict(desc.fields).get("kind")
    if isinstance(node, AtomDesc) and node.has_value and isinstance(node.value, str):
        return node.value
    return ""


def _atom(fields: dict, name: str) -> str:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value and node.value is not None:
        return str(node.value)
    return ""


def _num(fields: dict, name: str, default: float) -> float:
    node = fields.get(name)
    if isinstance(node, AtomDesc) and node.has_value and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    return float(default)


def _struct(fields: dict, name: str) -> dict:
    node = fields.get(name)
    if isinstance(node, StructDesc):
        return dict(node.fields)
    return {}


def _seq_strings(node: Desc | None) -> list[str]:
    if not isinstance(node, SequenceDesc):
        return []
    out = []
    for item in node.items:
        if isinstance(item, AtomDesc) and item.has_value and item.value is not None:
            out.append(str(item.value))
    return out


def _rows(node: Desc | None, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(node, SequenceDesc):
        return []
    rows = []
    for item in node.items:
        if not isinstance(item, StructDesc):
            continue
        fields = dict(item.fields)
        row: dict[str, Any] = {}
        for key in keys:
            raw = fields.get(key)
            if isinstance(raw, AtomDesc) and raw.has_value:
                row[key] = raw.value
            else:
                row[key] = ""
        rows.append(row)
    return rows


def _table(node: Desc | None) -> list[dict[str, Any]]:
    if not isinstance(node, SequenceDesc):
        return []
    rows = []
    for item in node.items:
        if not isinstance(item, StructDesc):
            continue
        row = {}
        for name, child in item.fields:
            if isinstance(child, AtomDesc) and child.has_value:
                row[str(name)] = child.value
        rows.append(row)
    return rows


_WORLD_JS = r"""
(function () {
  var el = document.getElementById("zw-spec");
  var canvas = document.getElementById("zw-view");
  var ui = document.getElementById("zw-ui");
  if (!el || !canvas) return;
  var spec = {};
  try { spec = JSON.parse(el.textContent || "{}"); } catch (err) { return; }
  var kernels = {"physics.body":1,"skeleton.rig":1,"film.cut":1,"cad.brep":1,"commerce.settle":1,"social.federate":1,"llm.weights":1};
  if (kernels[spec.kind]) {
    if (ui) ui.innerHTML = "<pre>" + JSON.stringify(spec, null, 2) + "</pre>";
    if (spec.kind !== "physics.body" && spec.kind !== "cad.brep") canvas.hidden = true;
  }
  var g = canvas.getContext("2d");
  var family = spec.family || "software";
  function clear(color) {
    g.fillStyle = color || "#111";
    g.fillRect(0, 0, canvas.width, canvas.height);
  }
  function label(text, y) {
    g.fillStyle = "#eee";
    g.font = "16px sans-serif";
    g.fillText(String(text || ""), 16, y || 28);
  }
  if (family === "game" || spec.kind === "scene" || spec.kind === "level") {
    var x = canvas.width / 2 + (spec.spawn && spec.spawn.x || 0) * 8;
    var y = canvas.height / 2 - (spec.spawn && spec.spawn.y || 0) * 8;
    var keys = {};
    function draw() {
      clear("#1b2430");
      g.fillStyle = "#6cf";
      g.fillRect(x - 16, y - 16, 32, 32);
      label((spec.mesh || spec.room || spec.kind) + "  arrows to move", 24);
    }
    window.addEventListener("keydown", function (ev) { keys[ev.key] = true; });
    window.addEventListener("keyup", function (ev) { keys[ev.key] = false; });
    setInterval(function () {
      if (keys.ArrowLeft || keys.a) x -= 4;
      if (keys.ArrowRight || keys.d) x += 4;
      if (keys.ArrowUp || keys.w) y -= 4;
      if (keys.ArrowDown || keys.s) y += 4;
      draw();
    }, 33);
    draw();
    return;
  }
  if (family === "cad" || spec.kind === "cad.solid" || spec.kind === "model3d" || spec.kind === "material") {
    clear("#222");
    var w = Math.max(20, (spec.width || 2) * 40);
    var h = Math.max(20, (spec.height || 2) * 40);
    g.fillStyle = spec.albedo || "#8ab";
    g.fillRect(220, 90, w, h);
    g.strokeStyle = "#fff";
    g.strokeRect(220, 90, w, h);
    g.beginPath();
    g.moveTo(220, 90);
    g.lineTo(220 + (spec.depth || 2) * 18, 90 - (spec.depth || 2) * 12);
    g.lineTo(220 + (spec.depth || 2) * 18 + w, 90 - (spec.depth || 2) * 12);
    g.lineTo(220 + w, 90);
    g.fillStyle = spec.albedo || "#9bc";
    g.fill();
    label((spec.mesh || spec.kind) + " solid", 24);
    return;
  }
  if (spec.kind === "animation" || spec.kind === "video" || spec.kind === "media.channel") {
    var t = 0;
    var duration = Number(spec.duration || 2);
    var frames = spec.keyframes || [];
    var clips = spec.clips || [spec.clip || spec.kind];
    function drawMedia() {
      clear("#100818");
      var p = duration ? (t % duration) / duration : 0;
      g.fillStyle = "#f6c";
      g.fillRect(20, 160, p * (canvas.width - 40), 12);
      g.fillStyle = "#fff";
      g.fillRect(40 + Math.sin(t * 3) * 80, 80, 48, 48);
      label((clips[0] || spec.kind) + "  " + p.toFixed(2), 24);
    }
    setInterval(function () { t += 0.05; drawMedia(); }, 50);
    if (ui) ui.innerHTML = "<p>" + (clips.join(" · ")) + "</p>";
    return;
  }
  if (spec.kind === "audio") {
    var btn = document.createElement("button");
    btn.textContent = "Play " + (spec.hz || 440) + " Hz";
    btn.addEventListener("click", function () {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.frequency.value = spec.hz || 440;
      gain.gain.value = spec.gain || 0.2;
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(); osc.stop(ctx.currentTime + 0.4);
    });
    if (ui) ui.appendChild(btn);
    clear("#111");
    label("audio runtime", 24);
    return;
  }
  if (spec.kind === "social.channel") {
    canvas.hidden = true;
    var log = (spec.messages || []).slice();
    function paint() {
      ui.innerHTML = "<h3>" + (spec.name || "channel") + "</h3><ul>" +
        log.map(function (m) { return "<li>" + String(m) + "</li>"; }).join("") +
        "</ul><input id='zw-msg' /><button type='button' id='zw-send'>Send</button>";
      var send = document.getElementById("zw-send");
      var box = document.getElementById("zw-msg");
      send.addEventListener("click", function () {
        if (box && box.value) { log.push(box.value); box.value = ""; paint(); }
      });
    }
    paint();
    return;
  }
  if (spec.kind === "commerce.checkout") {
    canvas.hidden = true;
    var total = 0;
    var items = spec.items || [];
    items.forEach(function (item) { total += Number(item.price || 0); });
    ui.innerHTML = "<h3>Checkout · " + (spec.currency || "usd") + "</h3><ul>" +
      items.map(function (item) {
        return "<li>" + item.name + " · " + item.price + "</li>";
      }).join("") + "</ul><p>Total " + total + "</p><button type='button' id='zw-pay'>Record charge</button><p id='zw-paid'></p>";
    var pay = document.getElementById("zw-pay");
    pay.addEventListener("click", function () {
      var key = "zw-ledger";
      var rows = [];
      try { rows = JSON.parse(localStorage.getItem(key) || "[]"); } catch (err) { rows = []; }
      rows.push({ total: total, currency: spec.currency, at: Date.now() });
      localStorage.setItem(key, JSON.stringify(rows));
      document.getElementById("zw-paid").textContent = "Recorded locally · " + rows.length + " charges";
    });
    return;
  }
  if (spec.kind === "ai") {
    canvas.hidden = true;
    ui.innerHTML = "<p>Model " + (spec.model || "local") + "</p><textarea id='zw-prompt' rows='4'>" +
      (spec.prompt || "") + "</textarea><button type='button' id='zw-run'>Complete</button><pre id='zw-out'></pre>";
    document.getElementById("zw-run").addEventListener("click", function () {
      var prompt = document.getElementById("zw-prompt").value || "";
      var words = prompt.trim().split(/\s+/).slice(0, 48).join(" ");
      document.getElementById("zw-out").textContent = (spec.model || "local") + " · " + words;
    });
    return;
  }
  if (spec.kind === "spreadsheet" || spec.kind === "data.table") {
    canvas.hidden = true;
    var rows = spec.rows || [];
    ui.innerHTML = "<table>" + rows.map(function (row) {
      return "<tr>" + Object.keys(row).map(function (k) { return "<td>" + row[k] + "</td>"; }).join("") + "</tr>";
    }).join("") + "</table>";
    return;
  }
  clear("#123");
  label(spec.kind + " · " + (spec.title || ""), 28);
})();
"""
