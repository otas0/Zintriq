#!/usr/bin/env bash
# Tokenized git fetch/reset when plain HTTPS to github.com:443 hangs or proxies 403/502.
# Usage: scripts/git-fetch-tokenized.sh [ref]
# Default ref: origin/main
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REF="${1:-main}"
TOKEN="$(gh auth token)"
ORIGIN_URL="$(git remote get-url origin)"
cleanup() {
  git remote set-url origin "$ORIGIN_URL"
}
trap cleanup EXIT
git remote set-url origin "https://x-access-token:${TOKEN}@github.com/otas0/Zintriq.git"
GIT_TERMINAL_PROMPT=0 git -c http.version=HTTP/1.1 fetch --prune origin "$REF" --tags
git reset --hard "origin/$REF"
git status -sb
git log -1 --oneline
