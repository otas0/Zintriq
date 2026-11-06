# Zintriq Editor (desktop)

Electron shell + local Flask (`ZINTRIQ_DESKTOP=1`) on `127.0.0.1`.

```bash
# from repo root
pip install -r requirements.txt
cd desktop && npm install && npm start
```

`npm install` runs `rebuild:pty` (node-pty → Electron 33 ABI). Needs a Python with `setuptools` (repo `.venv` works). If rebuild fails, Term falls back to Flask PTY (unix-pty / Windows ConPTY via pywinpty).

```bash
npm run rebuild:pty   # retry native PTY
npm run smoke
```

Home URL: `/editor`. Workspace files live under `ZINTRIQ_WORKSPACE` (default: `$ZINTRIQ_DATA_DIR/workspace`).

LSP servers are detected from `PATH` (pyright, typescript-language-server, gopls, rust-analyzer, clangd, …).
