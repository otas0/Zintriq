#!/usr/bin/env python3
"""Copy OFL text and emit THIRD_PARTY_NOTICES for the desktop bundle."""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OFL_CANDIDATES = (
    ROOT / "static" / "fonts" / "geist-sans" / "OFL.txt",
    ROOT / "desktop" / "resources" / "notices" / "OFL.txt",
)


def _resolve_ofl() -> Path | None:
    for path in OFL_CANDIDATES:
        if path.is_file():
            return path
    return None


def main() -> int:
    dest_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs")
    dest_dir.mkdir(parents=True, exist_ok=True)
    ofl = _resolve_ofl()
    if ofl is None:
        print(
            "missing OFL.txt (looked in static/fonts and desktop/resources/notices)",
            file=sys.stderr,
        )
        return 1
    ofl_copy = dest_dir / "OFL.txt"
    ofl_copy.write_bytes(ofl.read_bytes())
    lines = [
        "# Third-party notices",
        "",
        "This file is generated for the desktop bundle. Geist Sans remains under the SIL Open Font License.",
        "",
        "## Geist Sans",
        "",
        ofl.read_text(encoding="utf-8"),
        "",
        "## Python packages",
        "",
    ]
    for dist in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        license_text = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "UNKNOWN"
        lines.append(f"- {name} {dist.version}: {license_text.splitlines()[0][:200]}")
    dest = dest_dir / "THIRD_PARTY_NOTICES.md"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {dest} and {ofl_copy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
