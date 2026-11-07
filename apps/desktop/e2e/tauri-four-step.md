# Tauri four-step hand-test / future WebDriver

## Manual (current)

```bash
corepack pnpm --filter @zintriq/desktop exec tauri dev
```

Then in the window:

1. **打开文件夹** — pick a small C++ project (or empty dir with `main.cpp`)
2. **Allow** — grant filesystem permission if the OS prompts
3. **保存** — edit a file and save
4. Optional: **一键生成 stub** → **连接 clangd**

Automated half (no window): `pnpm smoke:tauri-four-step` (stub + real clangd diagnostics).

## WebDriver / Playwright (planned)

Tauri 2 can be driven with WebDriver (e.g. `tauri-driver` + WebDriverIO) or a custom CDP attach once the window is up. This repo’s Electron Playwright suite is **not** the Tauri shell — keep them separate:

| Suite | Shell | Port / entry |
|---|---|---|
| `pnpm verify:electron` | Electron + Vite UI | `:5175` |
| `pnpm smoke:tauri-four-step` | clangd via lsp-client | n/a |
| Future `e2e/tauri-*.spec.ts` | Tauri WebView | `tauri-driver` |

Do not reuse Electron `electron.launch` against the Tauri binary.
