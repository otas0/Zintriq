#!/usr/bin/env python3
"""Unit tests for sha256sums coverage (missing / extra / digest)."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "sha256sums.py"


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def run_sums(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


class Sha256SumsTests(unittest.TestCase):
    def test_write_and_verify_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "ZintriqEditor-0.1.12-mac-arm64.zip", b"zip")
            write(root / "ZintriqEditor-0.1.12-Setup.exe", b"exe")
            write(root / "app.AppImage", b"img")
            write(root / "noise.blockmap", b"bm")
            write(root / "SHA256SUMS-macos-latest", b"stale")
            proc = run_sums(str(root), "--write", "--verify")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse((root / "SHA256SUMS-macos-latest").exists())
            lines = (root / "SHA256SUMS").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 3)
            names = {line.split()[1] for line in lines}
            self.assertEqual(
                names,
                {
                    "ZintriqEditor-0.1.12-Setup.exe",
                    "ZintriqEditor-0.1.12-mac-arm64.zip",
                    "app.AppImage",
                },
            )

    def test_verify_missing_installer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.zip", b"a")
            write(root / "b.exe", b"b")
            digest_a = hashlib.sha256(b"a").hexdigest()
            (root / "SHA256SUMS").write_text(f"{digest_a}  a.zip\n", encoding="utf-8")
            proc = run_sums(str(root), "--verify")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("missing from SUMS", proc.stderr)
            self.assertIn("b.exe", proc.stderr)

    def test_verify_extra_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.zip", b"a")
            digest_a = hashlib.sha256(b"a").hexdigest()
            (root / "SHA256SUMS").write_text(
                f"{digest_a}  a.zip\n{'0'*64}  ghost.exe\n",
                encoding="utf-8",
            )
            proc = run_sums(str(root), "--verify")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("extra in SUMS", proc.stderr)
            self.assertIn("ghost.exe", proc.stderr)

    def test_verify_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.zip", b"a")
            (root / "SHA256SUMS").write_text(f"{'0'*64}  a.zip\n", encoding="utf-8")
            proc = run_sums(str(root), "--verify")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("digest mismatch", proc.stderr)


if __name__ == "__main__":
    unittest.main()
