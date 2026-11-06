# ADR 0002 — WASM sandbox

## Status

Accepted

## Decision

Extensions run inside a WASM guest in a separate worker. The manifest declares capabilities. Host functions for anything else throw `CapabilityDeniedError` and write an audit record `{ timestamp, extensionId, capability, action: "denied" }` through pino. `runExtension` defaults to a 10 second timeout and a 64MB memory limit. Timeout returns `EXTENSION_TIMEOUT`. Exceeding the memory limit returns `EXTENSION_OOM`.

## Engine

`@bytecodealliance/wasmtime` is not on the npm registry. The package named `wasmtime` is an unmaintained 0.0.2 stub and is not the Wasmtime runtime. This MVP therefore loads guest modules with the Node WebAssembly API inside `worker_threads`. Manifest validation, the audit record, and the error codes are unchanged.

## Consequences

There is no second execution mode that grants a guest the full editor process. A guest that needs a capability must list it, and reviewers can see that list in the release notes.
