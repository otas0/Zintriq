/** Customer storefront — hours, copy, carousel, search, distance */

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

document.addEventListener("DOMContentLoaded", () => {
  const copyBtn = document.getElementById("sf-copy-address");
  const addressEl = document.getElementById("sf-address-text");
  copyBtn?.addEventListener("click", async () => {
    const text = addressEl?.textContent?.trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = "✓";
      setTimeout(() => { copyBtn.textContent = "⎘"; }, 1500);
    } catch {
      window.prompt("Copy address:", text);
    }
  });

  const hoursToggle = document.getElementById("sf-hours-toggle");
  const hoursPanel = document.getElementById("sf-hours-panel");
  hoursToggle?.addEventListener("click", () => {
    const open = hoursPanel?.classList.toggle("hidden") === false;
    hoursToggle.setAttribute("aria-expanded", open ? "true" : "false");
    hoursToggle.textContent = open ? "−" : "+";
  });

  const track = document.getElementById("sf-deals-track");
  const prev = document.getElementById("sf-deals-prev");
  const next = document.getElementById("sf-deals-next");
  if (track) {
    const scrollBy = () => Math.min(track.clientWidth * 0.85, 380);
    prev?.addEventListener("click", () => track.scrollBy({ left: -scrollBy(), behavior: "smooth" }));
    next?.addEventListener("click", () => track.scrollBy({ left: scrollBy(), behavior: "smooth" }));
  }

  document.querySelectorAll('.sf-categories__link[href^="#"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      const id = link.getAttribute("href")?.slice(1);
      const target = id ? document.getElementById(id) : null;
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", `#${id}`);
    });
  });

  const searchInput = document.getElementById("sf-search");
  if (searchInput) {
    const sections = () => document.querySelectorAll(".sf-catalog__section");
    const tiles = () => document.querySelectorAll(".sf-tile[data-search]");
    const filter = () => {
      const q = searchInput.value.trim().toLowerCase();
      tiles().forEach((tile) => {
        const hay = tile.getAttribute("data-search") || "";
        tile.classList.toggle("sf-tile--hidden", q.length > 0 && !hay.includes(q));
      });
      sections().forEach((section) => {
        const visible = section.querySelectorAll(".sf-tile:not(.sf-tile--hidden)").length;
        section.classList.toggle("sf-catalog__section--empty", q.length > 0 && visible === 0);
      });
      const dealsBar = document.querySelector(".sf-deals-bar");
      if (dealsBar) {
        const dealTiles = dealsBar.querySelectorAll(".sf-tile");
        const anyVisible = [...dealTiles].some((t) => !t.classList.contains("sf-tile--hidden"));
        dealsBar.classList.toggle("sf-deals-bar--hidden", q.length > 0 && !anyVisible);
      }
    };
    searchInput.addEventListener("input", filter);
  }

  const sidebar = document.getElementById("sf-profile");
  const distanceEl = document.getElementById("sf-distance");
  const storeLat = parseFloat(sidebar?.dataset.storeLat || "");
  const storeLng = parseFloat(sidebar?.dataset.storeLng || "");
  if (distanceEl && Number.isFinite(storeLat) && Number.isFinite(storeLng) && navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const km = haversineKm(pos.coords.latitude, pos.coords.longitude, storeLat, storeLng);
        distanceEl.textContent = formatDistance(km);
        distanceEl.classList.remove("hidden");
      },
      () => {},
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  }
});
