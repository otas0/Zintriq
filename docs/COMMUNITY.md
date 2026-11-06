# Community

Four contribution types show up under their own headings in the release notes and on the community list. There is no automatic score. A maintainer copies the merged item into the matching heading.

## Core code PR

Changes to the editor, core service, build check, extension host, or LSP client. Non-trivial changes go through review. The release note lists the pull request title and the author under **核心代码**.

## HAL Mapping Pack

A declarative YAML board file: MCU family, toolchain command, pins, and peripherals. You do not need to change editor code. CI validates the schema, rejects unknown fields, and rejects two logical names on one physical pin. The release note lists the board id under **硬件适配包**.

## Diagnostic knowledge

A short note that explains a failed build check, plus the fix. Reviewed notes ship with the docs. The release note lists the diagnostic title under **诊断知识**.

## Extension

A WASM guest plus a manifest. The manifest must declare capabilities. Undeclared calls stay unavailable and are audited. The release note lists the extension id and the capability list under **扩展**.

## Release notes and the community list

Each release has four headings, one per type above. The community list uses the same four headings and the same text. Seed work from the core team is labeled as such. Nothing ranks contributors by points.
