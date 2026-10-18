"""Token helpers for the local inverted index: CJK, pinyin, fuzzy edits."""

from __future__ import annotations

import re

from desktop.pinyin_table import PHRASES, PINYIN, RADICALS, SYLLABLES, TRADITIONAL

_LATIN = re.compile(r"[a-z0-9_]{2,}")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def tokens(text: str) -> list[str]:
    raw = str(text or "")
    lower = raw.lower()
    out = _LATIN.findall(lower)
    chars = _CJK.findall(raw)
    for i, ch in enumerate(chars):
        out.append(ch)
        py = PINYIN.get(ch)
        if py:
            out.append(py)
            out.append(py + "1")
            out.append(py + "2")
            if py.startswith(("zh", "ch", "sh")):
                out.append(py[:2])
            else:
                out.append(py[:1])
        if i + 1 < len(chars):
            nxt = chars[i + 1]
            out.append(ch + nxt)
            py2 = PINYIN.get(nxt)
            if py and py2:
                out.append(py + py2)
            if i + 2 < len(chars):
                out.append(ch + nxt + chars[i + 2])
        simp = next((src for src, trad in TRADITIONAL.items() if trad == ch), "")
        if simp:
            out.append(simp)
            spy = PINYIN.get(simp)
            if spy:
                out.append(spy)
        trad = TRADITIONAL.get(ch)
        if trad:
            out.append(trad)
        for radical, bucket in RADICALS.items():
            if ch in bucket or ch == radical:
                out.append(radical)
                out.append(f"stroke:{len(bucket)}")
    for phrase, py in PHRASES.items():
        if phrase in raw:
            out.append(phrase)
            out.append(py)
    return out[:4000]


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 2:
        return 99
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        row = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            row.append(min(row[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = row
    return prev[-1]


def expand_query(token: str) -> list[str]:
    tok = re.sub(r"[1-5]$", "", str(token or "").strip().lower())
    if not tok:
        return []
    out = [tok, tok + "1", tok + "2", tok + "3", tok + "4"]
    for syll in SYLLABLES:
        if syll == tok or (len(tok) >= 2 and syll.startswith(tok)):
            out.append(syll)
    if len(tok) >= 3:
        for syll in SYLLABLES:
            if levenshtein(tok, syll) <= 1:
                out.append(syll)
    for phrase, py in PHRASES.items():
        if tok in {phrase, py} or py.startswith(tok):
            out.append(phrase)
            out.append(py)
    for simp, trad in TRADITIONAL.items():
        if tok in {simp, trad}:
            out.append(simp)
            out.append(trad)
            py = PINYIN.get(simp) or PINYIN.get(trad)
            if py:
                out.append(py)
    for ch, py in PINYIN.items():
        if tok == py or tok == ch or py.startswith(tok) or (len(tok) == 1 and py[:1] == tok):
            out.append(ch)
            out.append(py)
            out.append(py[:1])
    return list(dict.fromkeys(out))


def lookup(inv: dict, token: str) -> set[str]:
    hits: set[str] = set()
    for cand in expand_query(token):
        hits.update(inv.get(cand) or [])
    if hits:
        return hits
    if len(token) >= 3:
        for key, bucket in inv.items():
            if abs(len(key) - len(token)) <= 1 and levenshtein(token, key) <= 1:
                hits.update(bucket)
    return hits
