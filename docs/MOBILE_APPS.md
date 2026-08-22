# Zintriq — Mobile Apps (Android & iOS)

The **website stays as-is** (Flask on port 5001). Native apps are thin Capacitor shells that load the same `/app` UI from your server.

## What you get

| Platform | How |
|----------|-----|
| **Website** | `python3 app.py` → http://127.0.0.1:5001 |
| **PWA** | Install from browser (manifest + service worker) |
| **Android** | Capacitor → Google Play |
| **iOS** | Capacitor → App Store |

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

Native Android/iOS apps use a WebView that loads `https://your-domain.com/app` — the same Flask site you already run. No duplicate backend.

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
