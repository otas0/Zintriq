"""Editor view plugins for Workbench.

A view is a pane on Describe / Simulate / Instantiate / Space. Built-ins ship with
the meta core; extra views register here. Graph is the UIR drawing; instantiate
also emits a builder canvas node tree from the same page blocks.

Real plugins (not Meta services) declare contract render / hitTest / edit in JS.
The document is always Desc. Meta remains a built-in service, not a numbered editor.
"""

from __future__ import annotations

from dataclasses import dataclass


CONTRACT_PANE = ("activate",)
CONTRACT_PLUGIN = ("render", "hitTest", "edit")
CORE_VIEW_IDS = frozenset(
    {"space", "code", "visual", "graph", "diagram", "uir", "simulation", "page", "artifact"}
)

# 28 Workbench view plugins. Diagram ships separately; these 27 share one host.
# `meta` / `meta-meta` are views over Desc, not a second meta engine (`meta/` stays a service).
EDITOR_PLUGINS: tuple[tuple[str, str], ...] = (
    ("scene", "Scene"),
    ("node", "Node"),
    ("ui", "UI"),
    ("animation", "Animation"),
    ("shader", "Shader"),
    ("audio", "Audio"),
    ("level", "Level"),
    ("data", "Data"),
    ("logic", "Logic"),
    ("text", "Text"),
    ("vector", "Vector"),
    ("bitmap", "Bitmap"),
    ("model3d", "Model 3D"),
    ("material", "Material"),
    ("particle", "Particle"),
    ("terrain", "Terrain"),
    ("video", "Video"),
    ("font", "Font"),
    ("document", "Document"),
    ("spreadsheet", "Spreadsheet"),
    ("map", "Map"),
    ("circuit", "Circuit"),
    ("chip", "Chip"),
    ("quantum", "Quantum"),
    ("ai", "AI"),
    ("meta", "Meta"),
    ("meta-meta", "Meta-meta"),
)


def plugin_ids() -> tuple[str, ...]:
    return tuple(item[0] for item in EDITOR_PLUGINS)


@dataclass(frozen=True)
class EditorView:
    id: str
    name: str
    surfaces: tuple[str, ...]
    pane: str
    rank: int = 0
    contract: tuple[str, ...] = CONTRACT_PANE


_VIEWS: dict[str, EditorView] = {}


def register_view(view: EditorView) -> EditorView:
    key = str(view.id or "").strip()
    if not key or not str(view.name or "").strip() or not view.surfaces or not str(view.pane or "").strip():
        raise ValueError("editor view needs id, name, surfaces, and pane")
    steps = tuple(str(item).strip() for item in (view.contract or ()) if str(item).strip())
    if not steps:
        raise ValueError("editor view needs a contract")
    _VIEWS[key] = EditorView(
        id=view.id,
        name=view.name,
        surfaces=view.surfaces,
        pane=view.pane,
        rank=view.rank,
        contract=steps,
    )
    return _VIEWS[key]


def list_views(surface: str | None = None) -> list[dict]:
    wanted = str(surface or "").strip()
    rows = []
    for view in _VIEWS.values():
        if wanted and wanted not in view.surfaces:
            continue
        rows.append(
            {
                "id": view.id,
                "name": view.name,
                "pane": view.pane,
                "rank": view.rank,
                "surfaces": list(view.surfaces),
                "contract": list(view.contract),
            }
        )
    rows.sort(key=lambda item: (int(item["rank"]), item["id"]))
    return rows


def get_view(view_id: str) -> EditorView | None:
    return _VIEWS.get(str(view_id or "").strip())


def reset_views_for_tests() -> None:
    _VIEWS.clear()
    install_builtin_views()


def install_builtin_views() -> None:
    register_view(EditorView("space", "Space", ("space",), "space", 0))
    register_view(EditorView("code", "Code", ("describe", "space"), "code", 1))
    register_view(EditorView("visual", "Visual", ("describe", "simulate"), "visual", 1))
    register_view(EditorView("graph", "Graph", ("describe", "simulate", "space"), "graph", 2))
    register_view(EditorView("diagram", "Diagram", ("describe",), "diagram", 3, CONTRACT_PLUGIN))
    register_view(EditorView("uir", "UIR", ("describe", "space"), "uir", 4))
    register_view(EditorView("simulation", "Simulation", ("simulate",), "simulation", 0))
    register_view(EditorView("page", "Page", ("describe", "instantiate"), "page", 5))
    register_view(EditorView("artifact", "Artifact", ("instantiate",), "artifact", 6))
    for index, (plugin_id, name) in enumerate(EDITOR_PLUGINS):
        surfaces = ("describe", "simulate") if plugin_id in {"logic", "animation"} else ("describe",)
        register_view(
            EditorView(plugin_id, name, surfaces, "plugin", 20 + index, CONTRACT_PLUGIN)
        )


install_builtin_views()
