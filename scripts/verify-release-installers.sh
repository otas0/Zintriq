#!/usr/bin/env bash
# One-shot: download every ZintriqEditor installer from a GitHub Release and shasum -c.
# Prefers Azure-signed Range downloads (scripts/download-gh-artifact-ranges.py).
#
# Usage: scripts/verify-release-installers.sh [tag]
# Example: scripts/verify-release-installers.sh v0.1.12-release
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:-v0.1.12-release}"
DEST="${ROOT}/.tmp-verify-${TAG}"
mkdir -p "$DEST"
cd "$DEST"

echo "==> SHA256SUMS from $TAG"
gh release download "$TAG" -R otas0/Zintriq -p SHA256SUMS --clobber

count=0
while read -r _digest name; do
  [ -n "${name:-}" ] || continue
  count=$((count + 1))
  if [ -f "$name" ]; then
    echo "keep $name"
    continue
  fi
  # Prefer REST numeric asset ids — `gh release view --json` may return GraphQL node ids (RA_…).
  id="$(gh api "repos/otas0/Zintriq/releases/tags/${TAG}" --jq ".assets[]|select(.name==\"$name\")|.id")"
  if [ -z "$id" ] || [ "$id" = "null" ]; then
    echo "missing asset id for $name" >&2
    exit 1
  fi
  echo "==> download $name (asset $id)"
  python3 "$ROOT/scripts/download-gh-artifact-ranges.py" --release-asset-id "$id" -o "$name"
done < <(awk 'NF>=2 {print $1, $2}' SHA256SUMS)

echo "==> shasum -c ($count installers)"
shasum -a 256 -c SHA256SUMS
echo "OK $count installers for $TAG"
