# ADR 0005 — `GET /extensions` response shape

## Status

Accepted

## Context

Callers needed the active `ZINTRIQ_EXTENSIONS_DIR` when troubleshooting missing manifests. Returning only a bare array made that opaque.

## Decision

`GET /extensions` returns an object:

```json
{
  "extensions": [/* ExtensionManifest[] */],
  "extensionsDir": "/absolute/path"
}
```

It is **not** a JSON array. Old clients that did `await res.json()` and treated the result as `ExtensionInfo[]` must switch to `.extensions`.

Compatibility note for array clients: if `Array.isArray(body)` is true you are talking to a pre-ADR-0005 server; otherwise read `body.extensions` and optionally show `body.extensionsDir`.

## Consequences

Desktop, curl samples, Playwright mocks, and core-service tests use the object shape. Directory changes can also be observed over `GET /extensions/events` (SSE) without changing this document’s payload.
