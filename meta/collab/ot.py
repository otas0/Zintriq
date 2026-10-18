"""Character-level operational transform (insert / delete).

Retain-style ops come from a string diff. Absolute ops are transformed when
two replicas edit the same base. The live document still stores an RGA; OT is
how a replica turns a new plaintext into character inserts and deletes.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any


def diff_ops(old: str, new: str) -> list[dict[str, Any]]:
    old = str(old or "")
    new = str(new or "")
    ops: list[dict[str, Any]] = []
    matcher = SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            n = i2 - i1
            if n:
                ops.append({"op": "retain", "n": n})
        elif tag == "delete":
            ops.append({"op": "delete", "n": i2 - i1})
        elif tag == "insert":
            ops.append({"op": "insert", "s": new[j1:j2]})
        elif tag == "replace":
            if i2 > i1:
                ops.append({"op": "delete", "n": i2 - i1})
            if j2 > j1:
                ops.append({"op": "insert", "s": new[j1:j2]})
    return ops


def apply_ops_string(base: str, ops: list[dict[str, Any]]) -> str:
    base = str(base or "")
    out: list[str] = []
    cursor = 0
    for op in ops:
        kind = str(op.get("op") or "")
        if kind == "retain":
            n = int(op.get("n") or 0)
            out.append(base[cursor : cursor + n])
            cursor += n
        elif kind == "delete":
            cursor += int(op.get("n") or 0)
        elif kind == "insert":
            out.append(str(op.get("s") or ""))
        elif kind == "insert_abs":
            pass
    out.append(base[cursor:])
    return "".join(out)


def to_abs_ops(ops: list[dict[str, Any]], *, replica: str = "") -> list[dict[str, Any]]:
    pos = 0
    abs_ops: list[dict[str, Any]] = []
    for op in ops:
        kind = str(op.get("op") or "")
        if kind == "retain":
            pos += int(op.get("n") or 0)
        elif kind == "insert":
            text = str(op.get("s") or "")
            abs_ops.append({"op": "insert", "pos": pos, "replica": replica, "s": text})
            pos += len(text)
        elif kind == "delete":
            n = int(op.get("n") or 0)
            abs_ops.append({"op": "delete", "n": n, "pos": pos, "replica": replica})
    return abs_ops


def transform_pair(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Inclusion transform of two concurrent absolute ops."""
    a = dict(left)
    b = dict(right)
    a_kind = str(a.get("op") or "")
    b_kind = str(b.get("op") or "")
    if a_kind == "insert" and b_kind == "insert":
        ap = int(a.get("pos") or 0)
        bp = int(b.get("pos") or 0)
        if bp < ap or (bp == ap and str(b.get("replica") or "") > str(a.get("replica") or "")):
            a["pos"] = ap + len(str(b.get("s") or ""))
        else:
            b["pos"] = bp + len(str(a.get("s") or ""))
        return a, b
    if a_kind == "insert" and b_kind == "delete":
        ap = int(a.get("pos") or 0)
        bp = int(b.get("pos") or 0)
        bn = int(b.get("n") or 0)
        alen = len(str(a.get("s") or ""))
        if ap <= bp:
            b["pos"] = bp + alen
        elif ap >= bp + bn:
            a["pos"] = ap - bn
        else:
            a["pos"] = bp
        return a, b
    if a_kind == "delete" and b_kind == "insert":
        b2, a2 = transform_pair(b, a)
        return a2, b2
    if a_kind == "delete" and b_kind == "delete":
        ap = int(a.get("pos") or 0)
        an = int(a.get("n") or 0)
        bp = int(b.get("pos") or 0)
        bn = int(b.get("n") or 0)
        a_end = ap + an
        b_end = bp + bn
        if a_end <= bp:
            b["pos"] = bp - an
        elif b_end <= ap:
            a["pos"] = ap - bn
        else:
            a_start = ap
            b_start = bp
            new_a_start = min(a_start, b_start)
            new_b_start = min(a_start, b_start)
            overlap = max(0, min(a_end, b_end) - max(a_start, b_start))
            a["pos"] = new_a_start
            b["pos"] = new_b_start
            a["n"] = max(0, an - overlap)
            b["n"] = max(0, bn - overlap)
            if a_start > b_start:
                a["pos"] = b_start
            if b_start > a_start:
                b["pos"] = a_start
        return a, b
    return a, b


def transform_lists(
    left_ops: list[dict[str, Any]], right_ops: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left_out = [dict(op) for op in left_ops]
    right_out = [dict(op) for op in right_ops]
    for i, _left in enumerate(left_out):
        for j, _right in enumerate(right_out):
            left_out[i], right_out[j] = transform_pair(left_out[i], right_out[j])
    return left_out, right_out


def apply_abs_ops(base: str, ops: list[dict[str, Any]]) -> str:
    text = str(base or "")
    for op in ops:
        kind = str(op.get("op") or "")
        pos = int(op.get("pos") or 0)
        pos = max(0, min(pos, len(text)))
        if kind == "insert":
            s = str(op.get("s") or "")
            text = text[:pos] + s + text[pos:]
        elif kind == "delete":
            n = int(op.get("n") or 0)
            text = text[:pos] + text[pos + n :]
    return text


def merge_from_base(base: str, left: str, right: str, replica_left: str, replica_right: str) -> str:
    a = to_abs_ops(diff_ops(base, left), replica=replica_left)
    b = to_abs_ops(diff_ops(base, right), replica=replica_right)
    a2, b2 = transform_lists(a, b)
    return apply_abs_ops(apply_abs_ops(base, a2), b2)
