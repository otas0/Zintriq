# Zintriq Governance

Zintriq inherits three practices from successful open editor communities:

1. **RFC for every material change** — features land after public discussion, community signal, and core review.
2. **“Contributed by” in every release** — external work is credited in release notes; target is a healthy share of non-core PRs.
3. **Public issues only** — bugs and feature requests are tracked in the open.

Differentiation comes from treating **hardware assets** as first-class contributions, not only editor PRs.

## Contribution types (scored independently)

| Type | What it is | How it lands |
|------|------------|--------------|
| **Core code PR** | Editor, compile service, debug protocol | RFC → review → merge |
| **HAL Mapping Pack** | Board pin constraints, peripheral map, flash config (YAML/TOML) | Declarative PR + CI validation |
| **Diagnostic knowledge** | Failure explanations for hardware verify | Curated into built-in KB |

Each type appears separately in release notes and community leaderboards. A HAL pack author is as visible as a core PR author.

## Hardware RFCs

Adding an MCU family, changing HAL interfaces, or changing flash protocols requires a **Hardware RFC**. Review must include at least one **non-core hardware contributor** from the community pool.

## Extension trust model

- Default host: **WASM sandbox** with **capability declarations** (fs scope, network, device). Undeclared capabilities are unavailable.
- High-privilege adapters (compiler bridge, debug adapter) may run in a **supervised separate process** only after audit + ownership disclosure + resource quotas.
- Publisher ownership changes must be **prominently disclosed**; removed extension names have a **cooldown** before reuse.

## Seed vs community

Early HAL packs may be labeled **“core team seed”** — never presented as organic community output. Scale starts when CI makes external packs cheap to submit.
