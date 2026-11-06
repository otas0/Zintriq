# Contributing to Zintriq

You do **not** need to write editor code to be a first-class contributor.

## 1. Core code PR

Editor UI, local services, DAP/LSP bridges. Open an RFC for non-trivial changes. Follow existing Python/JS style and tests under `tests/`.

## 2. HAL Mapping Pack

Add a board under a declarative pack (YAML/TOML): pins, peripherals, flash profile. CI validates schema and conflict rules. No editor changes required.

Example shape (illustrative):

```yaml
board: esp32-devkitc
mcu_family: esp32
pins:
  LED: GPIO2
flash:
  protocol: esptool
  baud: 921600
```

## 3. Diagnostic knowledge

When hardware verification fails, document the failure mode and fix hint. Entries are reviewed before shipping in the built-in knowledge base.

## Visibility

Release notes list each type separately under **Contributed by**. Hardware RFC reviewers are drawn from contributors with accepted HAL packs.

See also: [GOVERNANCE.md](../../GOVERNANCE.md), [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md).
