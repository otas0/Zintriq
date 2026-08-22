/** Discover — search, map (Leaflet), geolocation sort */

function haversineKm(lat1, lng1, lat2, lng2) {
  const r = 6371;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dlat = ((lat2 - lat1) * Math.PI) / 180;
  const dlng = ((lng2 - lng1) * Math.PI) / 180;
  const a = Math.sin(dlat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dlng / 2) ** 2;
  return r * 2 * Math.asin(Math.sqrt(a));
}

function formatDistance(km) {
  if (km < 1) return `${Math.round(km * 1000)} m away`;
  return `${km.toFixed(1)} km away`;
}

function readStoresJson() {
  const el = document.getElementById("discover-stores-json");
  if (!el) return [];
  try {
    return JSON.parse(el.textContent || "[]");
  } catch {
    return [];
  }
}

function setDiscoverStatus(message) {
  const status = document.getElementById("discover-loc-status");
  if (status) status.textContent = message;
}

function applyDiscoverSort(lat, lng) {
  const list = document.getElementById("discover-store-list");
  if (!list) return;
  const items = [...list.querySelectorAll("[data-discover-item]")];
  const scored = items.map((item) => {
    const storeLat = parseFloat(item.dataset.storeLat || "");
    const storeLng = parseFloat(item.dataset.storeLng || "");
    let distanceKm = null;
    if (Number.isFinite(storeLat) && Number.isFinite(storeLng)) {
      distanceKm = haversineKm(lat, lng, storeLat, storeLng);
      item.dataset.distanceKm = String(distanceKm);
      const slot = item.querySelector(
        ".guest-discover__distance--live, .guest-discover__distance, .ch-ue-store__distance-live",
      );
      if (slot) {
        slot.textContent = formatDistance(distanceKm);
        slot.classList.remove("guest-discover__distance--live");
      }
    }
    return { item, distanceKm };
  });

  scored.sort((a, b) => {
    const aMissing = a.distanceKm === null;
    const bMissing = b.distanceKm === null;
    if (aMissing !== bMissing) return aMissing ? 1 : -1;
    if (a.distanceKm !== null && b.distanceKm !== null && a.distanceKm !== b.distanceKm) {
      return a.distanceKm - b.distanceKm;
    }
    return (a.item.dataset.name || "").localeCompare(b.item.dataset.name || "");
  });

  scored.forEach(({ item }) => list.appendChild(item));
}

function applyLiveSearch(query) {
  const q = query.trim().toLowerCase();
  const items = document.querySelectorAll("[data-discover-item]");
  let visible = 0;
  items.forEach((item) => {
    const hay = item.dataset.search || item.dataset.name || "";
    const show = !q || hay.includes(q);
    item.hidden = !show;
    if (show) visible += 1;
  });
  const countEl = document.getElementById("discover-result-count");
  if (countEl) {
    countEl.textContent = `${visible} shop${visible === 1 ? "" : "s"}`;
  }
  return visible;
}

let discoverMap = null;
let discoverMarkers = [];
let userMarker = null;

function clearMapMarkers() {
  discoverMarkers.forEach((m) => m.remove());
  discoverMarkers = [];
  if (userMarker) {
    userMarker.remove();
    userMarker = null;
  }
}

function initDiscoverMap(stores, userLat, userLng) {
  const mapEl = document.getElementById("discover-map");
  if (!mapEl || typeof L === "undefined") return null;

  if (discoverMap) {
    discoverMap.remove();
    discoverMap = null;
    clearMapMarkers();
  }

  const mappable = stores.filter((s) => s.lat != null && s.lng != null);
  const defaultLat = userLat ?? (mappable[0]?.lat ?? 1.3521);
  const defaultLng = userLng ?? (mappable[0]?.lng ?? 103.8198);

  discoverMap = L.map(mapEl, { scrollWheelZoom: true }).setView([defaultLat, defaultLng], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(discoverMap);

  const bounds = [];

  mappable.forEach((shop) => {
    const lat = parseFloat(shop.lat);
    const lng = parseFloat(shop.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    bounds.push([lat, lng]);

    const marker = L.marker([lat, lng]).addTo(discoverMap);
    const status = shop.is_open === true ? "Open" : shop.is_open === false ? "Closed" : "";
    const dist = shop.distance_label ? `<br>${shop.distance_label}` : "";
    marker.bindPopup(
      `<strong>${shop.name}</strong>${status ? `<br>${status}` : ""}${dist}<br><a href="${shop.storefront_url}">View menu →</a>`,
    );
    marker.on("click", () => marker.openPopup());
    discoverMarkers.push(marker);
  });

  if (Number.isFinite(userLat) && Number.isFinite(userLng)) {
    userMarker = L.circleMarker([userLat, userLng], {
      radius: 8,
      color: "#111",
      fillColor: "#3A86FF",
      fillOpacity: 1,
      weight: 2,
    }).addTo(discoverMap).bindPopup("You are here");
    bounds.push([userLat, userLng]);
  }

  if (bounds.length > 1) {
    discoverMap.fitBounds(bounds, { padding: [36, 36], maxZoom: 15 });
  } else if (bounds.length === 1) {
    discoverMap.setView(bounds[0], 14);
  }

  setTimeout(() => discoverMap?.invalidateSize(), 100);
  return discoverMap;
}

function setDiscoverView(mode) {
  const listPanel = document.getElementById("discover-list-panel");
  const mapPanel = document.getElementById("discover-map-panel");
  const buttons = document.querySelectorAll(".guest-discover__view-btn");
  const isMap = mode === "map";

  listPanel?.classList.toggle("hidden", isMap);
  mapPanel?.classList.toggle("hidden", !isMap);
  if (mapPanel) mapPanel.setAttribute("aria-hidden", isMap ? "false" : "true");

  buttons.forEach((btn) => {
    const active = btn.dataset.view === mode;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });

  if (isMap) {
    const root = document.getElementById("guest-discover");
    const userLat = parseFloat(root?.dataset.userLat || "");
    const userLng = parseFloat(root?.dataset.userLng || "");
    initDiscoverMap(readStoresJson(), userLat, userLng);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("discover-use-location");
  const searchInput = document.getElementById("discover-search") || document.getElementById("ch-hub-search-input");
  const params = new URLSearchParams(window.location.search);
  const paramLat = parseFloat(params.get("lat") || document.getElementById("guest-discover")?.dataset.userLat || "");
  const paramLng = parseFloat(params.get("lng") || document.getElementById("guest-discover")?.dataset.userLng || "");

  const runSort = (lat, lng, message) => {
    applyDiscoverSort(lat, lng);
    const root = document.getElementById("guest-discover");
    if (root) {
      root.dataset.userLat = String(lat);
      root.dataset.userLng = String(lng);
    }
    setDiscoverStatus(message);
    if (document.querySelector('.guest-discover__view-btn[data-view="map"]')?.classList.contains("is-active")) {
      initDiscoverMap(readStoresJson(), lat, lng);
    }
  };

  if (Number.isFinite(paramLat) && Number.isFinite(paramLng)) {
    runSort(paramLat, paramLng, "Sorted by distance");
  }

  btn?.addEventListener("click", () => {
    if (!navigator.geolocation) {
      setDiscoverStatus("Location is not available in this browser.");
      return;
    }
    setDiscoverStatus("Getting your location…");
    btn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        const next = new URL(window.location.href);
        next.searchParams.set("lat", String(latitude));
        next.searchParams.set("lng", String(longitude));
        window.history.replaceState(null, "", next.toString());
        runSort(latitude, longitude, "Sorted by distance");
        btn.disabled = false;
      },
      () => {
        setDiscoverStatus("Location denied — showing all listed shops.");
        btn.disabled = false;
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  });

  searchInput?.addEventListener("input", () => {
    applyLiveSearch(searchInput.value);
  });

  document.querySelectorAll(".guest-discover__view-btn").forEach((button) => {
    button.addEventListener("click", () => setDiscoverView(button.dataset.view || "list"));
  });

  if (window.location.hash === "#map") {
    setDiscoverView("map");
  }

  if (!Number.isFinite(paramLat) && btn && navigator.geolocation && !params.get("q")) {
    btn.click();
  }
});
