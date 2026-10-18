# Zintriq — Studio apps (desktop path / Android & iOS)

The **website** keeps Community, marketing, accounts, and published runtimes.  
**Zintriq Studio** (`/studio`) is the composition shell (Data / Interface / Logic / Connection / Publish). Native Capacitor shells load **Studio only**, not the full `/app` product OS.

## What you get

| Platform | How |
|----------|-----|
| **Website** | `python3 app.py` → http://127.0.0.1:5001 — Community at `/app/community` |
| **Studio (web entry)** | `/studio` — same APIs; intended desktop/native chrome |
| **PWA** | Optional install of published surfaces |
| **Android / iOS** | Capacitor → loads `/studio` |
| **Account link** | Same user (session or Studio Bearer token `zst_…`) across web Community and Studio |

## One-time setup

### 1. Icons

```bash
python3 scripts/generate_app_icons.py
```

### 2. Server URL for phones

Add to `.env.local` at repo root:

```bash
# Production
PUBLIC_BASE_URL=https://your-domain.com
MOBILE_SERVER_URL=https://your-domain.com

# Local dev (replace with your computer's LAN IP)
MOBILE_SERVER_URL=http://192.168.x.x:5001
```

Run Flask bound to all interfaces (default `HOST=0.0.0.0`).

### 3. Capacitor project

```bash
cd mobile
npm install
npm run config          # writes capacitor.config.json from .env.local
npx cap add android     # once
npx cap add ios         # once (macOS + Xcode)
npm run sync
```

### 4. Open native IDEs

```bash
npm run android   # Android Studio
npm run ios       # Xcode
```

Build and run on device/simulator from the IDE.

## Architecture

Native apps load `https://your-domain.com/studio`. Community import uses web handoff (`/studio?install=…` or `zintriq://studio?…`) so the marketplace stays in the system browser. Studio API tokens: `POST /api/studio/tokens` (browser session) then `Authorization: Bearer zst_…`.

## PWA (install from browser)

1. Open `/app` in Chrome (Android) or Safari (iOS)
2. **Add to Home Screen** / **Install app**

Manifest: `/manifest.webmanifest`

## Dev tips

| Target | MOBILE_SERVER_URL |
|--------|-------------------|
| Physical phone (same Wi‑Fi) | `http://<LAN-IP>:5001` |
| Android emulator | `http://10.0.2.2:5001` |
| iOS simulator | `http://127.0.0.1:5001` |

After changing URL: `cd mobile && npm run sync`
