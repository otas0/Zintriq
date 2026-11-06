# Core service

Fastify sidecar for the typed MVP. Default listen address is `127.0.0.1:4317`. Logs go through pino.

The existing Flask host in the repository root stays in place for the Electron editor. This service loads the HAL registry and runs build checks for `apps/desktop`.

```bash
corepack pnpm --filter core-service dev
```

```bash
curl -s http://127.0.0.1:4317/health
curl -s http://127.0.0.1:4317/boards
curl -s -X POST http://127.0.0.1:4317/build \
  -H 'content-type: application/json' \
  -d '{"boardId":"esp32","entryFile":"main.cpp","files":[{"path":"main.cpp","content":"int main(){return 0;}\n"}]}'
curl -s http://127.0.0.1:4317/extensions
curl -s -X POST http://127.0.0.1:4317/extensions/fixture-fs-read/run \
  -H 'content-type: application/json' \
  -d '{}'
curl -s -X POST http://127.0.0.1:4317/extensions/fixture-no-fs/run \
  -H 'content-type: application/json' \
  -d '{}'
```

`GET /health` returns `{ "status": "ok", "version", "uptimeMs" }`. `GET /boards` returns the `BoardConfig` list. `POST /build` returns a `BuildResult`. `GET /extensions` returns `{ extensions, extensionsDir }` and re-reads manifests from `ZINTRIQ_EXTENSIONS_DIR` (default `fixtures/extensions`) on every call. `GET /audit?limit=50&offset=0&extensionId=` pages capability-denied entries; `GET /audit?export=1&extensionId=` returns up to 5000 matching rows for download. Errors use `{ "code", "message", "details?" }`.

## Extensions SSE (`GET /extensions/events`)

Server-Sent Events for hot reload when the extensions directory changes:

1. On connect the server sends `{ type: "connected", extensionsDir, ids }`.
2. `fs.watch` debounces (~50ms) then emits `{ type: "extensions-changed", added, removed, ids, at }`.
3. Heartbeat: every **25s** a comment frame (`: ping`) keeps proxies from idle-closing the stream.

### Client reconnect strategy (desktop)

- Open `EventSource` to `/extensions/events`.
- On `error`, close the socket and reconnect with exponential backoff starting at **1s**, doubling up to **30s**.
- Successful `onopen` resets backoff to 1s.
- Treat `extensions-changed` as the signal to re-fetch `GET /extensions` and briefly highlight `added` ids.

```bash
# Manual stream smoke (Ctrl-C to stop)
curl -N http://127.0.0.1:4317/extensions/events
```

```bash
export ZINTRIQ_EXTENSIONS_DIR=$PWD/fixtures/extensions
curl -s 'http://127.0.0.1:4317/audit?limit=20'
curl -s 'http://127.0.0.1:4317/audit?export=1&extensionId=fixture-no-fs'
```
