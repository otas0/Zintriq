#!/usr/bin/env python3
"""
Download a GitHub Actions artifact or Release asset via the Azure-signed
redirect URL with parallel Range requests.

Prefer this over `curl` through a corporate CONNECT proxy (often 403).

Examples:
  python3 scripts/download-gh-artifact-ranges.py --artifact-id 13571842847 -o macos.zip
  python3 scripts/download-gh-artifact-ranges.py --release-asset-id 720468261 -o app.zip
"""

from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def gh_token() -> str:
    env = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if env:
        return env.strip()
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def signed_redirect(api_url: str, token: str, accept: str) -> str:
    parsed = urlparse(api_url)
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=60)
    conn.request(
        "GET",
        parsed.path + (f"?{parsed.query}" if parsed.query else ""),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "User-Agent": "zintriq-range-downloader",
        },
    )
    resp = conn.getresponse()
    if resp.status in (301, 302, 303, 307, 308):
        loc = resp.getheader("Location")
        resp.read()
        conn.close()
        if not loc:
            raise RuntimeError("redirect without Location")
        return loc
    body = resp.read(120)
    conn.close()
    raise RuntimeError(f"expected redirect, got {resp.status}: {body[:80]!r}")


def content_length(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return int(resp.headers["Content-Length"])


def fetch_range(url: str, start: int, end: int) -> bytes:
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


def download(url: str, out: Path, parts: int) -> None:
    size = content_length(url)
    print(f"size={size / 1e6:.1f}MB parts={parts}", flush=True)
    chunk = (size + parts - 1) // parts
    ranges = []
    for i in range(parts):
        start = i * chunk
        end = min(size - 1, (i + 1) * chunk - 1)
        if start <= end:
            ranges.append((start, end))
    buf = bytearray(size)
    done = [0]
    t0 = time.time()

    def work(se: tuple[int, int]) -> int:
        start, end = se
        data = fetch_range(url, start, end)
        buf[start : start + len(data)] = data
        done[0] += len(data)
        elapsed = max(time.time() - t0, 0.001)
        print(
            f"  +{len(data) / 1e6:.1f}MB  {done[0] / 1e6:.1f}/{size / 1e6:.1f}MB  "
            f"{done[0] / elapsed / 1e3:.0f}KB/s",
            flush=True,
        )
        return len(data)

    with concurrent.futures.ThreadPoolExecutor(max_workers=parts) as pool:
        list(pool.map(work, ranges))
    out.write_bytes(buf)
    print(f"wrote {out} ({out.stat().st_size})", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--artifact-id", type=int, help="Actions artifact id")
    src.add_argument("--release-asset-id", type=int, help="Release asset id")
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--parts", type=int, default=16)
    parser.add_argument("--repo", default="otas0/Zintriq")
    args = parser.parse_args()

    token = gh_token()
    if args.artifact_id:
        api = f"https://api.github.com/repos/{args.repo}/actions/artifacts/{args.artifact_id}/zip"
        accept = "application/vnd.github+json"
    else:
        api = f"https://api.github.com/repos/{args.repo}/releases/assets/{args.release_asset_id}"
        accept = "application/octet-stream"

    url = signed_redirect(api, token, accept)
    print(f"signed Azure URL ok ({url[:64]}…)", flush=True)
    download(url, args.output, args.parts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
