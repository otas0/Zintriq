# Desktop UI

Vite + React + Monaco on `http://localhost:5173`. Talks only to core-service HTTP.

```bash
corepack pnpm --filter core-service dev
corepack pnpm --filter desktop dev
```

- **打开文件夹** uses the Chromium directory picker when available.
- **构建检查** is explicit; no build-on-save.
- **连接语言服务** attaches a mock LSP transport; it does not call clangd/pylsp from the browser.
- Playwright e2e launches Electron from `desktop/node_modules/electron` and mocks `127.0.0.1:4317`.
