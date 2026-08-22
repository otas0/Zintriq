/** Horizontal venue rails — Uber Eats–style scroll + arrow controls. */

function initVenueRails() {
  document.querySelectorAll("[data-venue-rail]").forEach((rail) => {
    const wrap = rail.closest(".ch-venue-rail-wrap");
    if (!wrap) return;
    const prev = wrap.querySelector("[data-venue-rail-prev]");
    const next = wrap.querySelector("[data-venue-rail-next]");
    const nav = wrap.querySelector(".ch-venue-rail-nav");

    const step = () => Math.max(240, Math.floor(rail.clientWidth * 0.72));

    const updateNav = () => {
      if (!nav) return;
      const overflow = rail.scrollWidth > rail.clientWidth + 8;
      nav.hidden = !overflow;
      if (prev) prev.disabled = rail.scrollLeft <= 4;
      if (next) next.disabled = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 4;
    };

    prev?.addEventListener("click", () => {
      rail.scrollBy({ left: -step(), behavior: "smooth" });
    });
    next?.addEventListener("click", () => {
      rail.scrollBy({ left: step(), behavior: "smooth" });
    });
    rail.addEventListener("scroll", updateNav, { passive: true });
    window.addEventListener("resize", updateNav, { passive: true });
    updateNav();
  });
}

initVenueRails();
