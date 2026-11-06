# Architecture

Zintriq keeps the UI, the core service, and extension execution in separate packages and processes.

1. **Desktop UI** (`apps/desktop`, Tauri 2 + React + Monaco). It renders files and sends explicit user actions over HTTP. It does not import `@zintriq/extension-host`, `@zintriq/build-service`, or `@zintriq/hal-registry`.
2. **Core service** (`apps/core-service`, Fastify on `127.0.0.1:4317`). It loads the HAL registry, runs build checks, lists extension manifests, and calls `runExtension`.
3. **Extension worker** (`packages/extension-host`). Each `runExtension` call starts a Node worker, loads the guest WASM there, and terminates that worker on timeout or when the call finishes.

The existing Electron shell and Flask host remain for the earlier editor. They are not the process that executes WASM guests.

## Build check

The user presses **构建检查**. The UI sends `POST /build` with the current in-memory files. The core service loads the selected board and calls `compileCheck`. That function writes a temp directory, runs `board.toolchain.compiler` (`g++` or `gcc`) with the board flags, and parses compiler output into diagnostics. The default timeout is 30 seconds. Nothing builds on save, and nothing flashes a board.

## WASM capabilities

An extension manifest lists capabilities: `fs.read`, `fs.write`, `net`, `serial`, and `process`. The worker installs the real host function only when that capability is listed. A call to anything else throws `CapabilityDeniedError`. The audit record is:

```json
{ "timestamp": "2026-10-18T00:00:00.000Z", "extensionId": "fixture-no-fs", "capability": "fs.read", "action": "denied" }
```

The record is written with pino. Timeout returns `EXTENSION_TIMEOUT`. Growing past `memoryLimitMb` returns `EXTENSION_OOM`. There is no unsandboxed process path.

`@wasmtime` is not published for Node. The worker uses the Node WebAssembly API instead. The manifest, audit record, and error codes stay the same. See ADR 0002.

## Language servers

`createLspClient` speaks LSP JSON-RPC over a transport. Tests use an in-memory transport and do not start a language server. A real `clangd` or `pylsp` process is optional via `server: { command, args }`. The desktop app does not open an LSP session. DAP is a type placeholder and has no methods.

## HTTP contract

Desktop talks only to these core-service routes:

- `GET /health`
- `GET /boards`
- `POST /build`
- `GET /extensions` → `{ extensions, extensionsDir }` (ADR 0005)
- `GET /extensions/events` → SSE (`extensions-changed` via `fs.watch`)
- `GET /audit?limit=&offset=&extensionId=`
- `POST /extensions/:id/run`

Errors use `{ "code", "message", "details?" }`.
