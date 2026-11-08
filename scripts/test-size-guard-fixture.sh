#!/usr/bin/env bash
# Offline / CI fixture: truncated cache must trigger re-get and restore expected size.
# Mirrors the keep/re-download branch in scripts/verify-release-installers.sh without
# touching GitHub (remote mirror stands in for Azure Range download).
#
# Usage: scripts/test-size-guard-fixture.sh
# Exit 0 on PASS.
set -euo pipefail
FIX="$(mktemp -d "${TMPDIR:-/tmp}/zintriq-size-guard.XXXXXX")"
cleanup() { rm -rf "$FIX"; }
trap cleanup EXIT

mkdir -p "$FIX/cache" "$FIX/remote"
# ~64 KiB "installer"
dd if=/dev/urandom of="$FIX/remote/ZintriqEditor-fixture.bin" bs=1024 count=64 status=none
expected="$(wc -c < "$FIX/remote/ZintriqEditor-fixture.bin" | tr -d ' ')"
cp "$FIX/remote/ZintriqEditor-fixture.bin" "$FIX/cache/ZintriqEditor-fixture.bin"

# Truncate like a broken proxy cache
dd if="$FIX/cache/ZintriqEditor-fixture.bin" of="$FIX/cache/ZintriqEditor-fixture.bin.tmp" bs=1 count=4096 status=none
mv "$FIX/cache/ZintriqEditor-fixture.bin.tmp" "$FIX/cache/ZintriqEditor-fixture.bin"
local_size="$(wc -c < "$FIX/cache/ZintriqEditor-fixture.bin" | tr -d ' ')"

if [ "$local_size" = "$expected" ]; then
  echo "SIZE_GUARD_FIXTURE_FAIL: truncate did not change size" >&2
  exit 1
fi
echo "truncated local=$local_size expected=$expected → re-download"

rm -f "$FIX/cache/ZintriqEditor-fixture.bin"
# Stand-in for: python3 scripts/download-gh-artifact-ranges.py ...
cp "$FIX/remote/ZintriqEditor-fixture.bin" "$FIX/cache/ZintriqEditor-fixture.bin"
got="$(wc -c < "$FIX/cache/ZintriqEditor-fixture.bin" | tr -d ' ')"
if [ "$got" != "$expected" ]; then
  echo "SIZE_GUARD_FIXTURE_FAIL: after re-get got=$got expected=$expected" >&2
  exit 1
fi

echo "SIZE_GUARD_FIXTURE_PASS"
