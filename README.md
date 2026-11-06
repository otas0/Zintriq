# Zintriq

Local editor for software and board-level hardware work. Slow work runs only after an explicit action. There is no proactive assistant in this MVP.

Two hosts live in this repo:

- Existing Electron shell (`desktop/`) and Flask service (`app.py` on `127.0.0.1`, default port 8765).
- Typed MVP: Fastify core service (`apps/core-service`, port 4317) and Tauri/React/Monaco UI (`apps/desktop`).

## Layout

```text
packages/protocol         Zod schemas
packages/hal-registry     board YAML
packages/build-service    local g++/gcc check
packages/extension-host   WASM guest worker
packages/lsp-client       LSP client, DAP placeholder
apps/core-service         Fastify API
apps/desktop              Tauri + React + Monaco
fixtures/boards           esp32, esp32-c3, stm32, stm32f103, rp2040
fixtures/extensions       sample guest and manifests
```

Full local acceptance steps: [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md).

## Install

```bash
corepack pnpm install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd desktop && npm install
```

## Core service

Start this before the desktop dev server. Default address is `127.0.0.1:4317`.

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

`GET /health` returns `{ "status": "ok", "version", "uptimeMs" }`. `GET /boards` returns the board list. `POST /build` returns `{ "status", "diagnostics", "durationMs" }`. `GET /extensions` returns `{ "extensions", "extensionsDir" }` and re-reads manifests from disk on every request. `GET /audit?limit=50&extensionId=` returns the capability-denied audit tail (optional `extensionId` filter) plus `extensionsDir`. Errors return `{ "code", "message", "details?" }`.

Extension directory:

```bash
export ZINTRIQ_EXTENSIONS_DIR=/absolute/path/to/extensions
corepack pnpm --filter core-service dev
```

Default is `fixtures/extensions`. Manifests are re-read on each `GET /extensions` and `POST .../run`.

## Desktop

Start core-service first, then the UI on `http://localhost:5173`:

```bash
corepack pnpm --filter core-service dev
corepack pnpm --filter desktop dev
```

In Chromium, use **打开文件夹** / **新建文件** / **保存**（脏标记 `*`）。**连接语言服务** uses an in-app mock transport only; it does not auto-request on every keystroke. Real `clangd` / `pylsp` stay optional in `@zintriq/lsp-client` (`detectLanguageServers()`).

Tauri shell (requires a local Rust toolchain; no paid cloud account):

```bash
cd apps/desktop/src-tauri && cargo install tauri-cli --version "^2" --locked || true
cd apps/desktop && cargo tauri build
```

`cargo tauri` is not part of `pnpm build`. The web bundle is `pnpm --filter @zintriq/desktop build`.

Playwright smoke starts the Vite server and mocks core-service. The runner uses the repo’s Electron binary under `desktop/node_modules/electron` because Playwright’s Chromium CDN is often unreachable here. That Electron path is the supported smoke path:

```bash
cd desktop && npm install
corepack pnpm --filter desktop test:e2e
```

## 构建检查

`compileCheck` in `@zintriq/build-service` runs only when something calls it. It does not run on save.

- The compiler is `board.toolchain.compiler` (`g++` or `gcc` on `PATH`). Arguments are `board.toolchain.flags` followed by `entryFile`.
- Sources are written under a temporary directory. Absolute paths and any `..` segment are rejected.
- The default timeout is 30 seconds (`CompileCheckOptions.timeoutMs` overrides it). On timeout the child is killed and the result is `failed` with error code `BUILD_TIMEOUT`.
- A missing or non-executable compiler is `failed` with error code `COMPILER_NOT_FOUND`. Install `g++` or `gcc` and put it on `PATH`.
- A non-zero exit is `failed`. Parsed `g++`/`gcc` lines become diagnostics `{ file, line, column, severity, message }` where severity is `error`, `warning`, `note`, or `info`. If a line cannot be parsed, the original stderr is kept as one diagnostic and on `rawOutput`.

```text
main.cpp:3:12: error: expected ';' before '}' token
```

Mocked unit tests:

```bash
corepack pnpm --filter @zintriq/build-service test
```

Real `g++` checks (skipped when `g++` is absent):

```bash
corepack pnpm --filter @zintriq/build-service test:integration
```

## Tests

```bash
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
```

`pnpm test` builds workspace packages first, then runs Vitest. Real compiler checks are behind `ZINTRIQ_INTEGRATION=1` in `@zintriq/build-service`.

Flask host tests:

```bash
python -m unittest tests/test_editor_app.py
```

## Adding a board

Add `fixtures/boards/<id>.yaml`:

```yaml
id: esp32
name: ESP32 DevKitC
mcuFamily: esp32
toolchain:
  compiler: g++
  flags:
    - -std=c++17
    - -fsyntax-only
pins:
  LED: GPIO2
peripherals: []
```

`mcuFamily` is `esp32`, `stm32`, or `rp2040`. `toolchain.compiler` must be non-blank. Two logical names cannot share one physical pin. Unknown fields are rejected. `@zintriq/hal-registry` exposes `listBoards()` and `getBoard(id)`.

## Adding a WASM extension

Put `guest.wasm` and a manifest JSON in `fixtures/extensions/`:

```json
{
  "id": "fixture-fs-read",
  "name": "FS read fixture",
  "version": "0.1.0",
  "capabilities": ["fs.read"],
  "entryWasm": "fixture.wasm"
}
```

The guest exports `run(i32) -> i32`. Host imports live under the `host` module (`fs_read`, and the other capability names). A call without the matching capability is denied and audited. `runExtension` defaults to 10 seconds and 64MB. `POST /extensions/:id/run` accepts `{ "input", "timeoutMs", "memoryLimitMb" }`.

## Language servers

`createLspClient({ rootUri, languageId, transport })` covers initialize, didOpen, didChange, didClose, diagnostics, and dispose. Tests and CI use the in-memory / mock transport and do not start a language server. `detectLanguageServers()` probes `clangd` and `pylsp` on PATH; pass `server: { command: "clangd" }` only when you intentionally want a local process. DAP is a type placeholder and has no methods.

## Community

See `docs/COMMUNITY.md`. Contribution types: core PR, HAL Mapping Pack, diagnostic notes, and capability-scoped extensions. Each type has its own heading in the release notes and on the community list. There is no score.

## Electron editor

```bash
cd desktop && npm start
```
