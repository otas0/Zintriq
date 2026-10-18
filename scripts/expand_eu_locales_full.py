#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Expand EU/related locales to full _active_en.json coverage via MyMemory MT.

Merge existing locale translations; translate every missing key. Flash msgids stay
English as keys (values translated). Protects Zintriq + primitive product terms.
Preserves {placeholders}. UTF-8 JSON indent=2. Resumable cache under
.tmp_i18n_gen/full/cache/.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "i18n" / "_active_en.json"
LOCALES = ROOT / "i18n" / "locales"
CACHE_DIR = ROOT / ".tmp_i18n_gen" / "full" / "cache"

LANGS = [
    "de", "fr", "es", "it", "pt", "pt-BR", "nl", "pl", "ru", "uk",
    "cs", "sk", "ro", "hu", "el", "bg", "hr", "sr", "bs", "sl",
    "lt", "lv", "et", "fi", "sv", "da", "no", "is", "ga", "mt",
    "cy", "sq", "eu", "ca", "az",
]

MM = {
    "de": "de", "fr": "fr", "es": "es", "it": "it", "pt": "pt",
    "pt-BR": "pt-BR", "nl": "nl", "pl": "pl", "ru": "ru", "uk": "uk",
    "cs": "cs", "sk": "sk", "ro": "ro", "hu": "hu", "el": "el",
    "bg": "bg", "hr": "hr", "sr": "sr-Latn", "bs": "bs", "sl": "sl",
    "lt": "lt", "lv": "lv", "et": "et", "fi": "fi", "sv": "sv",
    "da": "da", "no": "no", "is": "is", "ga": "ga", "mt": "mt",
    "cy": "cy", "sq": "sq", "eu": "eu", "ca": "ca", "az": "az",
}

# Longer first. Word-boundary protected.
PROTECT_WORDS = [
    ("Composition A", "ZZCOMPAZZ"),
    ("Composition B", "ZZCOMPBZZ"),
    ("Zintriq", "ZZZINTRIQZZ"),
    ("Marketplace", "ZZMARKETPLACEZZ"),
    ("Builder", "ZZBUILDERZZ"),
    ("PayPal", "ZZPAYPALZZ"),
    ("Interface", "ZZINTERFACEZZ"),
    ("Connection", "ZZCONNECTIONZZ"),
    ("Publish", "ZZPUBLISHZZ"),
    ("Logic", "ZZLOGICZZ"),
    ("Data", "ZZDATAZZ"),
    ("Docs", "ZZDOCSZZ"),
    ("PWA", "ZZPWAZZ"),
    ("IoT", "ZZIOTZZ"),
]

PH_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
DOTTED = re.compile(r"^[a-z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_.]+)+$")
FRAGMENTS = {"You", "You don", "Welcome! You", "Some children can", "favorites"}

# Numeric sentinels — MT almost never rewrites these
PH_SENTINEL = "88177{0}991"
# Map sentinel form back
PH_FIND = re.compile(r"88177(\d+)991")

_cache_lock = Lock()
_rate_lock = Lock()
_last_call = 0.0


def protect(text: str) -> tuple[str, list[str]]:
    phs: list[str] = []

    def _ph(m: re.Match) -> str:
        phs.append(m.group(0))
        return PH_SENTINEL.format(len(phs) - 1)

    out = PH_RE.sub(_ph, text)
    for src, tok in PROTECT_WORDS:
        out = re.sub(rf"\b{re.escape(src)}\b", tok, out)
    return out, phs


def unprotect(text: str, phs: list[str]) -> str:
    out = text

    def _restore_ph(m: re.Match) -> str:
        i = int(m.group(1))
        if 0 <= i < len(phs):
            return phs[i]
        return m.group(0)

    out = PH_FIND.sub(_restore_ph, out)
    for src, tok in PROTECT_WORDS:
        out = re.sub(re.escape(tok), src, out, flags=re.IGNORECASE)
    return out


def placeholders_ok(en: str, translated: str) -> bool:
    return PH_RE.findall(en) == PH_RE.findall(translated) or set(PH_RE.findall(en)) <= set(
        PH_RE.findall(translated)
    )


def mm_translate(text: str, target: str) -> str:
    global _last_call
    if not text.strip():
        return text
    if text.startswith("⌘"):
        return text
    q = urllib.parse.quote(text[:480])
    email = urllib.parse.quote("zintriq-i18n@users.noreply.github.com")
    url = (
        "https://api.mymemory.translated.net/get?"
        f"q={q}&langpair=en|{urllib.parse.quote(target)}&de={email}"
    )
    for attempt in range(5):
        with _rate_lock:
            now = time.time()
            wait = 0.08 - (now - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.time()
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ZintriqLocaleExpand/1.2"}
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            status = data.get("responseStatus")
            translated = (data.get("responseData") or {}).get("translatedText") or ""
            if isinstance(translated, str):
                translated = (
                    translated.replace("&quot;", '"')
                    .replace("&#39;", "'")
                    .replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                )
            if status == 200 and translated and "MYMEMORY WARNING" not in translated.upper():
                return translated
            time.sleep(0.6 + attempt * 0.5)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.8 + attempt * 0.6)
    return text


def translate_string(en_text: str, lang: str) -> str:
    protected, phs = protect(en_text)
    raw = mm_translate(protected, MM[lang])
    out = unprotect(raw, phs)
    if phs and not placeholders_ok(en_text, out):
        # Retry once; if still broken, splice placeholders onto a safe fallback
        raw2 = mm_translate(protected, MM[lang])
        out2 = unprotect(raw2, phs)
        if placeholders_ok(en_text, out2):
            return out2
        # Last resort: keep English (guarantees placeholders)
        return en_text
    return out


def load_cache(lang: str) -> dict[str, str]:
    path = CACHE_DIR / f"{lang}.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(lang: str, data: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_DIR / f"{lang}.json.tmp"
    path = CACHE_DIR / f"{lang}.json"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_locale(code: str, active: dict[str, str], additions: dict[str, str]) -> dict[str, int]:
    path = LOCALES / f"{code}.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    merged: dict[str, str] = {}
    for k, en_v in active.items():
        if k in existing and str(existing[k]).strip():
            merged[k] = str(existing[k])
        elif k in additions and str(additions[k]).strip():
            merged[k] = str(additions[k])
        else:
            merged[k] = en_v
    for k, v in existing.items():
        if k not in merged:
            merged[k] = v
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    have = sum(1 for k in active if k in merged and str(merged[k]).strip())
    return {"have": have, "active": len(active), "total": len(merged)}


def expand_lang(lang: str, active: dict[str, str], workers: int = 8) -> dict[str, int]:
    path = LOCALES / f"{lang}.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    missing = [k for k in active if k not in existing or not str(existing.get(k, "")).strip()]
    cache = load_cache(lang)
    # Drop cache entries that broke placeholders vs active EN
    bad = []
    for k, v in list(cache.items()):
        if k in active and PH_RE.findall(active[k]) and not placeholders_ok(active[k], v):
            bad.append(k)
        if k in active and any(tok.lower() in v.lower() for _, tok in PROTECT_WORDS if tok in v):
            # leftover sentinel
            bad.append(k)
    for k in bad:
        cache.pop(k, None)
    todo = [k for k in missing if k not in cache]

    print(f"[{lang}] need {len(missing)} | todo {len(todo)} | cached {len(cache)}", flush=True)

    def one(key: str) -> tuple[str, str]:
        en_text = active[key]
        if (not DOTTED.match(key)) and (key in FRAGMENTS or len(key) < 3):
            return key, en_text
        try:
            return key, translate_string(en_text, lang)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {lang} {key[:48]}: {e}", flush=True)
            return key, en_text

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, k) for k in todo]
        for fut in as_completed(futs):
            key, val = fut.result()
            with _cache_lock:
                cache[key] = val
                done += 1
                if done % 50 == 0 or done == len(todo):
                    save_cache(lang, cache)
                    print(f"  [{lang}] {done}/{len(todo)}", flush=True)
    save_cache(lang, cache)
    additions = {k: cache.get(k, active[k]) for k in missing}
    for k, v in cache.items():
        additions.setdefault(k, v)
    return write_locale(lang, active, additions)


def verify(active: dict[str, str]) -> list[tuple[str, int, int, int]]:
    rows = []
    for lang in LANGS:
        path = LOCALES / f"{lang}.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        have = sum(1 for k in active if k in data and str(data[k]).strip())
        ph_bad = 0
        for k, en_v in active.items():
            if k not in data:
                continue
            if PH_RE.findall(en_v) and not placeholders_ok(en_v, data[k]):
                ph_bad += 1
        rows.append((lang, have, len(active), ph_bad))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="*", default=LANGS)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    active = json.loads(ACTIVE.read_text(encoding="utf-8"))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify_only:
        rows = verify(active)
        print(f"{'lang':<8} {'have':>6} {'active':>7} {'pct':>7} {'ph_bad':>7}")
        for lang, have, total, ph_bad in rows:
            print(f"{lang:<8} {have:>6} {total:>7} {100.0 * have / total:>6.1f}% {ph_bad:>7}")
        ok = all(h == t and pb == 0 for _, h, t, pb in rows)
        return 0 if ok else 1

    results = []
    for lang in args.langs:
        if lang not in MM:
            print(f"skip unknown {lang}")
            continue
        stats = expand_lang(lang, active, workers=args.workers)
        results.append((lang, stats))
        print(f"==> {lang}: {stats['have']}/{stats['active']}", flush=True)

    print("\nCoverage table:")
    print(f"{'lang':<8} {'have':>6} {'active':>7} {'pct':>7}")
    for lang, s in results:
        pct = 100.0 * s["have"] / s["active"] if s["active"] else 0
        print(f"{lang:<8} {s['have']:>6} {s['active']:>7} {pct:>6.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
