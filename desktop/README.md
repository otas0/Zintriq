# Zintriq Studio (desktop)

Electron shell for the composition Studio. Community stays on the website.

## Dev

```bash
cd desktop
npm install
npm run dev
```

`npm run dev` starts Electron only. Electron launches Flask from the repo virtualenv (`../.venv` on macOS and Linux, `../.venv/Scripts/python.exe` on Windows) and does not expect a second Flask process. If that interpreter is missing, the window says to create the virtualenv and install dependencies.

Dev data is stored in the `Zintriq-dev` userData directory, separate from a packaged install. Close the window on macOS leaves the app running; on Windows and Linux closing the window quits and stops Flask.

## Tests

Same commands as CI, from the repo root. CI runs this on Python 3.11 for Windows, macOS, and Ubuntu, and runs the unit tests again on Ubuntu with Python 3.9.

macOS and Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
cd desktop
npm ci
npm run smoke
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
cd desktop
npm ci
npm run smoke
```

On Linux, `npm run smoke` runs itself under `xvfb-run`. Ubuntu CI invokes `xvfb-run -a npm run smoke` and sets `ZINTRIQ_SMOKE_XVFB=1` so the script does not wrap twice. Smoke passes `--no-sandbox` only when `CI=true` on Linux. Local runs and the packaged app keep the Electron sandbox on.

Desktop Studio can export and import `.zintriq` packages. Checksums prove the bytes were not changed; they do not prove who authored the package. See `docs/project-packages.md`.

Installers, Gatekeeper, AppArmor, `appId`, hashed Python lockfiles, and pack CI are documented in `docs/desktop-packaging.md`. Do not ship public installers until `appId` is a domain you own, reversed.


## Auth0 (Native + PKCE)

1. Auth0 → Applications → **Native**
2. Allowed Callback URLs: `zintriq://auth/callback`
3. Allowed Logout URLs: `zintriq://`
4. Token Endpoint Auth Method: **None**
5. Grant: Authorization Code, Refresh Token (`offline_access`)
6. Set `AUTH0_NATIVE_CLIENT_ID` on the Flask host (and in `.env.desktop.json`)

Desktop never embeds the Auth0 client secret. It opens the system browser, receives `zintriq://auth/callback`, then calls `POST /api/studio/auth/pkce/exchange`.

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
| **Community (web)** | Discover / import packages — never embedded in the shell |
| **Workspace / tenant** | Thin isolation boundary only — not a compose module |

Deep links: `zintriq://studio?action=install&package=…` opens Studio with an install handoff.
