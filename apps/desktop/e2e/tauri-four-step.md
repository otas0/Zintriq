# Tauri four-step: hand-test + automation

## Manual

```bash
pnpm --filter @zintriq/core-service start   # :4317
corepack pnpm --filter @zintriq/desktop exec tauri dev   # Vite :5173
```

1. **打开文件夹** — pick `/tmp/zintriq-handtest` (or any dir with `main.cpp`)
2. **Allow** — OS / `allow_project_dir` grant
3. **保存** — edit + save
4. Optional: stub → **连接 clangd**

Half-automated (no window): `pnpm smoke:tauri-four-step`.

## Automated four-step — `pnpm e2e:tauri-webdriver`

```bash
cargo install tauri-driver          # used on Linux/Windows
corepack pnpm --filter @zintriq/desktop exec tauri build --debug
pnpm e2e:tauri-webdriver
```

| Platform | Mechanism |
|---|---|
| Linux / Windows | `tauri-driver` WebDriver → click `[data-testid="open-folder"]` / `save-file`; path via `window.__ZINTRIQ_E2E_PROJECT__` |
| **macOS** | `tauri-driver` **unsupported** → host four-step: `ZINTRIQ_E2E_PROJECT_DIR` + `.zintriq-e2e-autosave` → Rust `allow_project_dir` + write `main.cpp` + `.zintriq-e2e-done` (UI also listens for the same env/event) |

Interactive hand-test (real dialog + OS allow) still required once per machine; Computer Use needs Accessibility enabled.

## Ports (do not mix)

| Suite | Shell | Port |
|---|---|---|
| `pnpm verify:electron` | Electron + Vite | **`:5175`** fixed (`e2e/ui-url.ts`, `reuseExistingServer: false`) |
| `tauri dev` | Tauri + Vite | `:5173` (`tauri.conf.json` `devUrl`) |
| `pnpm e2e:tauri-webdriver` | Tauri binary | driver `:4444` (Linux/Win) |

Never point Electron Playwright at `:5173`. Never `electron.launch` the Tauri binary.
