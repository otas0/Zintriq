/** Customer hub — minimal in-store header (scroll polish only). */

function initHeaderScroll() {
  const header = document.getElementById("ch-hub-header");
  if (!header) return;
  const onScroll = () => {
    header.classList.toggle("is-scrolled", window.scrollY > 4);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
}

initHeaderScroll();
