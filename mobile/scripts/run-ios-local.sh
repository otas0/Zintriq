#!/usr/bin/env bash
# Run Business OS on iOS Simulator (Mac local dev).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/mobile"

export MOBILE_SERVER_URL="${MOBILE_SERVER_URL:-http://127.0.0.1:5001}"

echo "→ Server URL: $MOBILE_SERVER_URL/app"
echo "→ Ensure Flask is running: python3 app.py (from repo root)"
echo ""

npm run config
npx cap sync ios

TARGET="${1:-iPhone 17}"
if [[ "$TARGET" =~ ^[0-9A-Fa-f-]{36}$ ]]; then
  npx cap run ios --target "$TARGET"
else
  UUID="$(xcrun simctl list devices available | grep "$TARGET" | head -1 | sed -n 's/.*(\([0-9A-F-]*\)).*/\1/p')"
  if [[ -z "$UUID" ]]; then
    echo "Simulator not found: $TARGET"
    xcrun simctl list devices available | grep iPhone
    exit 1
  fi
  npx cap run ios --target "$UUID"
fi
