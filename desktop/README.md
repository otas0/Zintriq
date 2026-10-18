# Zintriq Studio (desktop)

Electron shell for the meta factory. Community lives only in this desktop app.

## Dev

```bash
cd desktop
npm install
npm run dev
```

`npm run dev` starts Electron only. Electron launches Flask from the repo virtualenv (`../.venv` on macOS and Linux, `../.venv/Scripts/python.exe` on Windows) and does not expect a second Flask process. If that interpreter is missing, the window says to create the virtualenv and install dependencies.

Dev data is stored in the `Zintriq-dev` userData directory, separate from a packaged install. Close the window on macOS leaves the app running; on Windows and Linux closing the window quits and stops Flask.

## Tests

Same commands as CI, from the repo root. Supported Python is **3.9 through 3.12**. CI runs this on Python 3.11 for Windows, macOS, and Ubuntu, and runs the unit tests again on Ubuntu with Python 3.9.

macOS and Linux:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
cd desktop
npm ci
npm run smoke
```

Windows (PowerShell):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
cd desktop
npm ci
npm run smoke
```

On Linux, `npm run smoke` runs itself under `xvfb-run`. Ubuntu CI invokes `xvfb-run -a npm run smoke` and sets `ZINTRIQ_SMOKE_XVFB=1` so the script does not wrap twice. Smoke passes `--no-sandbox` only when `CI=true` on Linux. Local runs and the packaged app keep the Electron sandbox on.

Desktop Studio can export and import `.zintriq` packages. Checksums prove the bytes were not changed; they do not prove who authored the package. See `docs/project-packages.md`.

`npm run pack` writes an **unsigned** directory build (`--dir --publish never`). That is a local recipe, not a second product binary. Store installers wait until the product is complete and you set `CSC_LINK` / `APPLE_ID`.

If `ZINTRIQ_DATA_DIR/desktop/zintriq/launch.json` exists, Electron reads `/studio`, editors, and loopback-only flags from it. Missing that file keeps the current start path.

Local model files go in `ZINTRIQ_DATA_DIR/models`. GGUF needs `ZINTRIQ_LLAMA_BIN`. A `local-weights` JSON table is enough for fixture inference. `/api/ai`, `/api/ai/chat`, `/api/ai/embed`, and `/api/ai/tools` stay desktop-only. Missing weights return 4xx.

Community lists published descriptions **and** the local plugin store. Install a plugin, build a project from it, then submit another plugin. Engine, World, and AI are publishable forms on that loop. That loop stays on this machine (`127.0.0.1`), not a CDN.


## Account (Stage 2)

Desktop opens the system browser to the public Flask site:

1. Login opens the **local** website Flask on `http://127.0.0.1:5001` (run `python app.py`, no `ZINTRIQ_DESKTOP=1`). It does not use Cloudflare, `PUBLIC_BASE_URL`, or any public hostname. The Electron child process 404s `/desktop/authorize`.
2. File → Log in… opens `/desktop/authorize` with Authorization Code + PKCE (`zintriq-desktop`, callback `zintriq://auth/callback`).
3. After you Allow, the app exchanges the code at `POST /api/desktop/token` on that same origin.
4. The website verifies the account (`/login` or `/register`, then `/desktop/authorize`). The app stores the session in Electron `session.json` and **does not open Studio until that session is valid**. File → Log out returns to the sign-in gate. The cloud token is **not** sent as `Authorization` to local 127.0.0.1 meta APIs. After sign-in, saves still go to `ZINTRIQ_DATA_DIR` first; cloud sync must not block a local save.
5. Saving a description also PUTs the draft to the public origin when signed in. File → Sync now pulls. File → Publish… creates `/c/<id>` and opens it in the browser. File → Community lists published descriptions by kind (system, boundary, page, site, machine), shows your account and published work, and can publish the current description. File → Check for updates… on a **signed packaged app** downloads and installs; `electron .` only opens `/download`.

The local Flask process (`ZINTRIQ_DESKTOP=1`) returns 404 for `/desktop/authorize`, `/api/desktop/token`, `/api/desktop/cloud/*`, `/api/desktop/updates`, `/c/<id>`, `/w/<id>`, and `/status`.

## Build installers (for website download)

```bash
npm run dist:mac    # → desktop/release/*.dmg
npm run dist:win
npm run dist:linux
```

Copy artifacts to your CDN / GitHub Releases and set:

```bash
STUDIO_DOWNLOAD_MAC_URL=https://…
STUDIO_DOWNLOAD_WIN_URL=https://…
STUDIO_DOWNLOAD_LINUX_URL=https://…
```

The marketing page `/download` reads these URLs.

## Product split (keep this sharp)

| Surface | Owns |
|---------|------|
| **Studio (this app)** | Compose Data · Interface · Logic · Connection · Publish |
| **Community (this app)** | Discover / import creator packages |
| **Website** | Marketing, download, account — no Community page |
| **Workspace / tenant** | Thin isolation boundary only — not a compose module |

Deep links: `zintriq://studio?action=install&package=…` opens Studio with an install handoff.
