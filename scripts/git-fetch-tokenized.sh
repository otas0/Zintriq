#!/usr/bin/env bash
# Tokenized git fetch/reset when plain HTTPS to github.com:443 hangs or proxies 403/502.
# Usage: scripts/git-fetch-tokenized.sh [ref]
# Default ref: origin/main
#
# Prefer HTTP/1.1 + lowSpeed limits so a dead CONNECT proxy fails in ~45s instead of hanging.
# If Cursor's sandbox proxy 403s api.github.com, run this outside the IDE sandbox / with a
# working system proxy (or SSH: git remote set-url origin git@github.com:otas0/Zintriq.git).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REF="${1:-main}"
ORIGIN_URL="$(git remote get-url origin)"
# Prefer gh credential helper over embedding a token in the remote URL.
gh auth setup-git >/dev/null
ASKPASS="$(mktemp)"
cleanup() {
  rm -f "$ASKPASS"
  # leave origin URL untouched (HTTPS); helper supplies creds
}
trap cleanup EXIT
cat >"$ASKPASS" <<'EOF'
#!/bin/sh
case "$1" in
  *Username*) echo "x-access-token" ;;
  *Password*) gh auth token ;;
  *) exit 1 ;;
esac
EOF
chmod 700 "$ASKPASS"
# Normalize to HTTPS if someone left an SSH remote without Zintriq deploy-key access.
case "$ORIGIN_URL" in
  git@github.com:*|ssh://git@github.com/*)
    git remote set-url origin https://github.com/otas0/Zintriq.git
    ;;
esac
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="$ASKPASS" SSH_ASKPASS="$ASKPASS" DISPLAY="${DISPLAY:-:0}" \
  git \
  -c http.version=HTTP/1.1 \
  -c http.lowSpeedLimit=1000 \
  -c http.lowSpeedTime=45 \
  -c http.postBuffer=524288000 \
  -c credential.helper= \
  fetch --prune origin "$REF" --tags
git reset --hard "origin/$REF"
# Drop temporary grafts used when fetch was broken (safe if none).
if [ -d .git/refs/replace ] && [ -n "$(git replace -l 2>/dev/null || true)" ]; then
  echo "removing temporary git replace refs:"
  git replace -l
  git replace -l | while read -r oid; do git replace -d "$oid"; done
fi
git status -sb
git log -1 --oneline
