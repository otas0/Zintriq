#!/usr/bin/env bash
# Expose local Flask (port 5001) over HTTPS so Google Calendar can push webhooks.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-5001}"
ENV_FILE="$ROOT/.env.local"
LOG_FILE="$ROOT/.cloudflared-tunnel.log"
PID_FILE="$ROOT/.cloudflared-tunnel.pid"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Installing cloudflared (one-time)…"
  brew install cloudflared
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Tunnel already running (pid $(cat "$PID_FILE")). Log: $LOG_FILE"
  grep -o 'https://[^ ]*trycloudflare.com' "$LOG_FILE" 2>/dev/null | tail -1 || true
  exit 0
fi

: > "$LOG_FILE"
cloudflared tunnel --url "http://127.0.0.1:${PORT}" >>"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

PUBLIC_URL=""
for _ in $(seq 1 30); do
  PUBLIC_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" | head -1 || true)"
  if [[ -n "$PUBLIC_URL" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "Could not read tunnel URL. See $LOG_FILE"
  exit 1
fi

python3 - "$ENV_FILE" "$PUBLIC_URL" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
url = sys.argv[2].rstrip("/")
text = path.read_text(encoding="utf-8") if path.is_file() else ""
if re.search(r"^PUBLIC_BASE_URL=", text, flags=re.M):
    text = re.sub(r"^PUBLIC_BASE_URL=.*$", f"PUBLIC_BASE_URL={url}", text, flags=re.M)
else:
    text = text.rstrip() + f"\nPUBLIC_BASE_URL={url}\n"
path.write_text(text, encoding="utf-8")
print(f"Updated {path} → PUBLIC_BASE_URL={url}")
PY

echo ""
echo "HTTPS tunnel: $PUBLIC_URL"
echo "Webhook URL:  $PUBLIC_URL/api/integrations/google-calendar/webhook"
echo ""
echo "Restart Flask (python3 app.py), then in Settings → Integrations click Sync now once"
echo "to register the Google push channel."
echo ""
echo "Stop tunnel: kill \$(cat $PID_FILE)"
