# ADR 0001 — Monorepo

## Status

Accepted

## Decision

Domain code lives in a pnpm workspace:

- `packages/protocol`, `hal-registry`, `build-service`, `extension-host`, `lsp-client`
- `apps/core-service` (Fastify)
- `apps/desktop` (Tauri + React)

The Electron app under `desktop/` and the Flask host `app.py` stay where they are.

## Consequences

Shared schemas are Zod objects in `@zintriq/protocol`. Apps depend on packages through the workspace. CI runs lint, typecheck, test, and build from the repository root.
