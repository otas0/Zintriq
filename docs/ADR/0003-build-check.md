# ADR 0003 — Build check

## Status

Accepted

## Decision

Compile checking is explicit. `compileCheck` writes sources to a temp directory and runs the board toolchain (`g++` / `gcc` plus flags) with a 30 second timeout. Diagnostics keep file, line, column, severity, and message. Unparsed compiler output is kept on the result.

## Consequences

The editor does not compile on save and does not flash a board. A missing local compiler becomes a failed result with a clear message.
