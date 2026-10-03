#!/usr/bin/env python3
"""Emit a CycloneDX 1.5 SBOM for the Python environment used to freeze the server."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from uuid import uuid4


def main() -> int:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "sbom.cdx.json")
    components = []
    for dist in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        license_text = dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
        components.append(
            {
                "type": "library",
                "name": name,
                "version": dist.version,
                "bom-ref": f"pkg:pypi/{name}@{dist.version}",
                "licenses": [{"license": {"name": license_text.splitlines()[0][:200]}}] if license_text else [],
            }
        )
    doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "component": {"type": "application", "name": "zintriq-studio", "version": "0.1.0"},
        },
        "components": components,
    }
    dest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"wrote {dest} ({len(components)} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
