"""PWA manifest and mobile app configuration — website unchanged, apps load same /app UI."""

from __future__ import annotations

import json
import os

from flask import jsonify, send_from_directory


def register_mobile_platform(app) -> None:
    @app.get("/manifest.webmanifest")
    def pwa_manifest():
        payload = {
            "name": "Zintriq",
            "short_name": "Zintriq",
            "description": "Create customer experiences and manage your business",
            "start_url": "/app/store",
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait-primary",
            "background_color": "#FFFFFF",
            "theme_color": "#FFD500",
            "icons": [
                {"src": "/static/safari-touch-icon-yellow.png", "sizes": "180x180", "type": "image/png", "purpose": "any"},
                {"src": "/static/safari-tab-icon-yellow.png", "sizes": "32x32", "type": "image/png", "purpose": "any"},
                {"src": "/static/icons/icon-192.png?v=20260822y", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/static/icons/icon-512.png?v=20260822y", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": "/static/icons/icon-512.png?v=20260822y", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        }
        return app.response_class(
            json.dumps(payload),
            mimetype="application/manifest+json",
        )

    @app.get("/api/mobile/config")
    def mobile_config():
        base = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
        return jsonify({
            "app_name": "Zintriq",
            "start_path": "/app/store",
            "api_base": base or None,
            "min_version": "1.0.0",
        })

    @app.get("/sw.js")
    def service_worker():
        return app.response_class(
            """const CACHE = 'bos-v6-yellow';
self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll([
    '/static/safari-tab-icon-yellow.png',
    '/static/icons/icon-192.png?v=20260822y',
  ])));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  // Never intercept page navigations — network handles HTML; avoids "Offline" placeholder pages.
  if (e.request.mode === 'navigate') return;
  const accept = e.request.headers.get('accept') || '';
  if (accept.includes('text/html')) return;
  if (url.pathname.startsWith('/api/')) return;
  if (!url.pathname.startsWith('/static/')) return;
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
""",
            mimetype="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )
