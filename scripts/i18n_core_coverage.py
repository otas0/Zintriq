"""Print core-page translation coverage for each locale catalog.

Coverage is the share of site_config.CORE_MESSAGE_KEYS present in that file.
The language picker uses the same count and I18N_SELECTOR_COVERAGE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from site_config import CORE_MESSAGE_KEYS, I18N_SELECTOR_COVERAGE  # noqa: E402


def coverage_for(catalog: dict) -> float:
    if not CORE_MESSAGE_KEYS:
        return 1.0
    hit = sum(1 for key in CORE_MESSAGE_KEYS if catalog.get(key))
    return hit / len(CORE_MESSAGE_KEYS)


def main() -> None:
    locale_dir = ROOT / "i18n" / "locales"
    rows = []
    for path in sorted(locale_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        ratio = coverage_for({str(k): v for k, v in data.items()})
        rows.append((ratio, path.stem))
    rows.sort(key=lambda item: (-item[0], item[1]))
    print(f"threshold {I18N_SELECTOR_COVERAGE:.0%}  core keys {len(CORE_MESSAGE_KEYS)}")
    for ratio, code in rows:
        mark = "listed" if ratio + 1e-9 >= I18N_SELECTOR_COVERAGE else "url-only"
        print(f"{code}\t{ratio:.1%}\t{mark}")


if __name__ == "__main__":
    main()
