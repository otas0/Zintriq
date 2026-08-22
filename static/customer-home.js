/** Customer home — distance labels for nearby shop cards */

import { readLatLng, requestGeolocation, reloadWithLocation } from "./customer-hub-topbar.js";

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
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(1)} km`;
}

function applyHomeDistances(lat, lng) {
  document.querySelectorAll(".ch-ue-store[data-store-lat][data-store-lng]").forEach((card) => {
    const storeLat = parseFloat(card.dataset.storeLat || "");
    const storeLng = parseFloat(card.dataset.storeLng || "");
    const slot = card.querySelector(".ch-ue-store__distance-live");
    if (!slot || !Number.isFinite(storeLat) || !Number.isFinite(storeLng)) return;
    slot.textContent = formatDistance(haversineKm(lat, lng, storeLat, storeLng));
  });
}

function initHomeLocation() {
  const root = document.getElementById("ch-home");
  if (!root) return;

  const { lat, lng } = readLatLng();
  const savedLat = parseFloat(root.dataset.userLat || "");
  const savedLng = parseFloat(root.dataset.userLng || "");
  const useLat = lat ?? (Number.isFinite(savedLat) ? savedLat : null);
  const useLng = lng ?? (Number.isFinite(savedLng) ? savedLng : null);
  if (useLat != null && useLng != null) {
    applyHomeDistances(useLat, useLng);
  }

  const emptyBtn = document.getElementById("ch-home-set-location");
  emptyBtn?.addEventListener("click", () => {
    requestGeolocation(
      (latVal, lngVal) => reloadWithLocation(latVal, lngVal),
      () => document.getElementById("ch-hub-location-open")?.click(),
    );
  });
}

initHomeLocation();
