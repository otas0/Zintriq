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

`GET /health` returns `{ "status": "ok", "version", "uptimeMs" }`. `GET /boards` returns the `BoardConfig` list. `POST /build` returns a `BuildResult`. `GET /extensions` returns `{ extensions, extensionsDir }` and re-reads manifests from `ZINTRIQ_EXTENSIONS_DIR` (default `fixtures/extensions`) on every call. `GET /audit?limit=50&extensionId=` returns recent capability-denied audit entries (optional filter) for troubleshooting. Errors use `{ "code", "message", "details?" }`.

```bash
export ZINTRIQ_EXTENSIONS_DIR=$PWD/fixtures/extensions
curl -s 'http://127.0.0.1:4317/audit?limit=20'
```
