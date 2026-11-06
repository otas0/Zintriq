# Deployment — Zintriq Editor

Zintriq Editor is a **local desktop app**. There is no merchant/portal deploy in this tree.

## Desktop package

See [desktop-packaging.md](./desktop-packaging.md).

- Bind: `127.0.0.1` only
- Auth: random `ZINTRIQ_DESKTOP_TOKEN` per launch
- Data: `ZINTRIQ_DATA_DIR` (configurable)

## Recovery of pre-pivot product

Tag `archive/pre-editor-pivot` holds the previous merchant / meta / BOS / portal tree.
