"""Workbench layout v2: editor groups like a VS Code grid, stored in the session file."""

from __future__ import annotations


def _normalize_recent_map(raw: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    by = raw.get("recentByWorkspace") if isinstance(raw.get("recentByWorkspace"), dict) else {}
    for key, ids in by.items():
        ws = str(key or "default").strip()[:64] or "default"
        if not isinstance(ids, list):
            continue
        out[ws] = [str(x).strip()[:80] for x in ids if str(x).strip()][:8]
    ws = str(raw.get("workspace") or "default").strip()[:64] or "default"
    cmds = raw.get("recentCommands")
    if isinstance(cmds, list) and ws not in out:
        out[ws] = [str(x).strip()[:80] for x in cmds if str(x).strip()][:8]
    return out


def normalize_layout(layout: dict | None) -> dict:
    raw = layout if isinstance(layout, dict) else {}
    groups = raw.get("groups") if isinstance(raw.get("groups"), list) else []
    tree = raw.get("tree")
    if not groups and tree:
        groups = [{"editors": _editors_from_tree(tree), "id": "g0", "max": raw.get("max") or "", "size": 1, "tree": tree}]
    elif not groups:
        groups = [{"editors": [{"id": "code", "preview": False}], "id": "g0", "max": "", "size": 1, "tree": {"id": "code", "type": "leaf"}}]
    out = []
    for i, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        tree = group.get("tree") or {"id": "code", "type": "leaf"}
        editors = group.get("editors") if isinstance(group.get("editors"), list) else _editors_from_tree(tree)
        if not editors:
            editors = [{"id": "code", "preview": False}]
        out.append(
            {
                "activeEditor": str(group.get("activeEditor") or (editors[0].get("id") if editors else "code")),
                "editors": editors,
                "id": str(group.get("id") or f"g{i}"),
                "max": str(group.get("max") or ""),
                "size": float(group.get("size") or 1),
                "tree": tree,
            }
        )
    active = int(raw.get("activeGroup") or 0)
    if active < 0 or active >= len(out):
        active = 0
    current = out[active]
    workspace = str(raw.get("workspace") or "default")
    recents = _normalize_recent_map(raw)
    return {
        "activeGroup": active,
        "groups": out,
        "max": current.get("max") or raw.get("max") or "",
        "orientation": str(raw.get("orientation") or "horizontal"),
        "tree": current.get("tree"),
        "version": 8,
        "workspace": workspace,
        "pane": str(raw.get("pane") or ""),
        "modesScroll": max(0, int(raw.get("modesScroll") or 0)),
        "pinned": [str(x) for x in raw.get("pinned") or []],
        "activity": str(raw.get("activity") or "explorer"),
        "sidebar": bool(raw["sidebar"]) if "sidebar" in raw else True,
        "panel": max(0.12, min(0.8, float(raw.get("panel") or 0.28))),
        "zen": bool(raw.get("zen") or False),
        "panelTab": str(raw.get("panelTab") or "output"),
        "columns": max(1, min(3, int(raw.get("columns") or 1))),
        "profiles": raw.get("profiles") if isinstance(raw.get("profiles"), dict) else {},
        "mru": [str(x) for x in raw.get("mru") or []],
        "sidebarWidth": max(0.12, min(0.5, float(raw.get("sidebarWidth") or 0.22))),
        "auxiliary": bool(raw.get("auxiliary") or False),
        "sticky": [str(x) for x in raw.get("sticky") or []],
        "queries": _normalize_queries(raw.get("queries")),
        "recentByWorkspace": recents,
        "recentCommands": recents.get(workspace, []),
    }


def _normalize_queries(raw) -> list[dict]:
    rows = []
    if not isinstance(raw, list):
        return [
            {"id": "unstamped", "stamped": "0", "slug": ""},
            {"id": "scene", "kind": "scene", "slug": ""},
        ]
    for item in raw[:24]:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or item.get("kind") or item.get("stamped") or "query").strip()[:64]
        if not ident:
            continue
        rows.append(
            {
                "id": ident,
                "form": str(item.get("form") or "")[:32],
                "kind": str(item.get("kind") or "")[:64],
                "fingerprint": str(item.get("fingerprint") or "")[:64],
                "stamped": str(item.get("stamped") or "")[:16],
                "meta_level": str(item.get("meta_level") or "")[:8],
                "meta_level_min": str(item.get("meta_level_min") or "")[:8],
                "meta_level_max": str(item.get("meta_level_max") or "")[:8],
                "slug": str(item.get("slug") or "")[:80],
            }
        )
    return rows


def split_group(layout: dict, *, direction: str = "right") -> dict:
    state = normalize_layout(layout)
    current = dict(state["groups"][state["activeGroup"]])
    incoming = {
        "activeEditor": current["activeEditor"],
        "editors": list(current["editors"]),
        "id": f"g{len(state['groups'])}",
        "max": "",
        "size": current["size"],
        "tree": current["tree"],
    }
    if direction in {"left", "up"}:
        state["groups"].insert(state["activeGroup"], incoming)
    else:
        state["groups"].insert(state["activeGroup"] + 1, incoming)
        state["activeGroup"] += 1
    state["orientation"] = "vertical" if direction in {"up", "down"} else "horizontal"
    return normalize_layout(state)


def move_editor(layout: dict, editor_id: str, group_index: int) -> dict:
    state = normalize_layout(layout)
    ident = str(editor_id or "")
    dest = max(0, min(int(group_index), len(state["groups"]) - 1))
    for group in state["groups"]:
        group["editors"] = [row for row in group["editors"] if str(row.get("id")) != ident]
    state["groups"][dest]["editors"].append({"id": ident, "preview": False})
    state["groups"][dest]["activeEditor"] = ident
    state["activeGroup"] = dest
    state["groups"] = [group for group in state["groups"] if group["editors"]] or state["groups"]
    return normalize_layout(state)


def close_group(layout: dict, group_index: int | None = None) -> dict:
    state = normalize_layout(layout)
    idx = state["activeGroup"] if group_index is None else int(group_index)
    if len(state["groups"]) <= 1:
        return state
    if 0 <= idx < len(state["groups"]):
        state["groups"].pop(idx)
    state["activeGroup"] = min(state["activeGroup"], len(state["groups"]) - 1)
    return normalize_layout(state)


def _editors_from_tree(tree: dict | None) -> list[dict]:
    ids: list[str] = []

    def walk(node):
        if not isinstance(node, dict):
            return
        kind = str(node.get("type") or "")
        if kind == "stack":
            ids.extend(str(item) for item in node.get("ids") or [])
            return
        if kind == "split":
            walk(node.get("a"))
            walk(node.get("b"))
            return
        ident = str(node.get("id") or "")
        if ident:
            ids.append(ident)

    walk(tree)
    return [{"id": ident, "preview": False} for ident in dict.fromkeys(ids)]


def resize_group(layout: dict, group_index: int, size: float) -> dict:
    state = normalize_layout(layout)
    idx = max(0, min(int(group_index), len(state["groups"]) - 1))
    state["groups"][idx]["size"] = max(0.1, float(size))
    return normalize_layout(state)


def pin_editor(layout: dict, editor_id: str) -> dict:
    state = normalize_layout(layout)
    ident = str(editor_id or "")
    pinned = list(state.get("pinned") or [])
    if ident and ident not in pinned:
        pinned.append(ident)
    state["pinned"] = pinned
    return normalize_layout(state)


def unpin_editor(layout: dict, editor_id: str) -> dict:
    state = normalize_layout(layout)
    ident = str(editor_id or "")
    state["pinned"] = [item for item in state.get("pinned") or [] if item != ident]
    return normalize_layout(state)


def close_tab(layout: dict, editor_id: str) -> dict:
    state = normalize_layout(layout)
    ident = str(editor_id or "")
    for group in state["groups"]:
        group["editors"] = [row for row in group["editors"] if str(row.get("id")) != ident]
        if str(group.get("activeEditor")) == ident and group["editors"]:
            group["activeEditor"] = group["editors"][0].get("id")
        elif not group["editors"]:
            group["editors"] = [{"id": "code", "preview": False}]
            group["activeEditor"] = "code"
    return normalize_layout(state)


def set_chrome(
    layout: dict,
    *,
    sidebar: bool | None = None,
    panel: float | None = None,
    zen: bool | None = None,
    activity: str | None = None,
    panel_tab: str | None = None,
    columns: int | None = None,
) -> dict:
    state = normalize_layout(layout)
    if sidebar is not None:
        state["sidebar"] = bool(sidebar)
    if panel is not None:
        state["panel"] = float(panel)
    if zen is not None:
        state["zen"] = bool(zen)
    if activity is not None:
        state["activity"] = str(activity)
    if panel_tab is not None:
        state["panelTab"] = str(panel_tab)
    if columns is not None:
        state["columns"] = int(columns)
    return normalize_layout(state)


def save_profile(layout: dict, name: str) -> dict:
    state = normalize_layout(layout)
    ident = str(name or "default") or "default"
    profiles = dict(state.get("profiles") or {})
    profiles[ident] = {
        "activity": state["activity"],
        "auxiliary": state["auxiliary"],
        "columns": state["columns"],
        "groups": state["groups"],
        "orientation": state["orientation"],
        "panel": state["panel"],
        "panelTab": state["panelTab"],
        "sidebar": state["sidebar"],
        "sidebarWidth": state["sidebarWidth"],
        "sticky": state["sticky"],
        "zen": state["zen"],
    }
    state["profiles"] = profiles
    state["workspace"] = ident
    return normalize_layout(state)


def apply_profile(layout: dict, name: str) -> dict:
    state = normalize_layout(layout)
    ident = str(name or "")
    row = (state.get("profiles") or {}).get(ident)
    if not isinstance(row, dict):
        return state
    merged = {**state, **row, "profiles": state["profiles"], "workspace": ident}
    return normalize_layout(merged)


def remember_editor(layout: dict, editor_id: str) -> dict:
    state = normalize_layout(layout)
    ident = str(editor_id or "")
    mru = [item for item in state.get("mru") or [] if item != ident]
    if ident:
        mru.insert(0, ident)
    state["mru"] = mru[:24]
    return normalize_layout(state)


def stick_editor(layout: dict, editor_id: str) -> dict:
    state = normalize_layout(layout)
    ident = str(editor_id or "")
    sticky = list(state.get("sticky") or [])
    if ident and ident not in sticky:
        sticky.append(ident)
    state["sticky"] = sticky
    return normalize_layout(state)


def maximize_editor(layout: dict, editor_id: str | None = None) -> dict:
    state = normalize_layout(layout)
    ident = str(editor_id or "")
    if not ident:
        group = state["groups"][state["activeGroup"]]
        ident = str(group.get("activeEditor") or "")
    current = str(state.get("max") or "")
    state["max"] = "" if current == ident else ident
    state["groups"][state["activeGroup"]]["max"] = state["max"]
    return normalize_layout(state)


def cycle_mru(layout: dict, *, offset: int = 1) -> dict:
    state = remember_editor(layout, str(state_id(layout)))
    mru = list(state.get("mru") or [])
    if len(mru) < 2:
        return state
    nxt = mru[max(0, min(len(mru) - 1, int(offset)))]
    return focus_editor(state, nxt)


def state_id(layout: dict) -> str:
    state = normalize_layout(layout)
    group = state["groups"][state["activeGroup"]]
    return str(group.get("activeEditor") or "")


def focus_editor(layout: dict, editor_id: str) -> dict:
    state = normalize_layout(layout)
    ident = str(editor_id or "")
    for i, group in enumerate(state["groups"]):
        ids = [str(row.get("id")) for row in group.get("editors") or []]
        if ident in ids:
            group["activeEditor"] = ident
            state["activeGroup"] = i
            break
    return remember_editor(state, ident)


def focus_group(layout: dict, group_index: int) -> dict:
    state = normalize_layout(layout)
    state["activeGroup"] = max(0, min(int(group_index), len(state["groups"]) - 1))
    return normalize_layout(state)


def swap_groups(layout: dict, a: int, b: int) -> dict:
    state = normalize_layout(layout)
    ia = max(0, min(int(a), len(state["groups"]) - 1))
    ib = max(0, min(int(b), len(state["groups"]) - 1))
    groups = list(state["groups"])
    groups[ia], groups[ib] = groups[ib], groups[ia]
    state["groups"] = groups
    return normalize_layout(state)


def reset_layout(layout: dict | None = None) -> dict:
    return normalize_layout({"groups": [], "workspace": "default", "profiles": (layout or {}).get("profiles") if isinstance(layout, dict) else {}})
