/** Deferred motion — CSS-first, no layout-blocking work. */

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function staggerHomeCards() {
  if (prefersReducedMotion()) return;
  const home = document.querySelector(".ch-home");
  if (!home) return;
  home.querySelectorAll(".ch-animate-in").forEach((el, i) => {
    el.style.setProperty("--ch-enter-delay", `${Math.min(i * 70, 350)}ms`);
    el.classList.add("ch-animate-in--ready");
  });
}

function initCustomerMotion() {
  const page = document.querySelector(".ch-hub-page");
  if (page && !prefersReducedMotion()) {
    page.classList.add("mq-page-enter");
    page.addEventListener(
      "animationend",
      () => page.classList.add("mq-page-enter--done"),
      { once: true }
    );
  }

  staggerHomeCards();

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      const btn = form.querySelector(
        '.mq-btn-primary[type="submit"], .ig-profile__btn--primary[type="submit"]'
      );
      if (!btn || btn.disabled) return;
      btn.classList.add("is-loading");
      btn.setAttribute("aria-busy", "true");
    });
  });

  document.querySelectorAll(".ch-tabbar__item").forEach((link) => {
    link.addEventListener("click", () => {
      if (prefersReducedMotion()) return;
      link.classList.add("is-pressed");
      window.setTimeout(() => link.classList.remove("is-pressed"), 180);
    });
  });

  const header = document.getElementById("ch-hub-header") || document.getElementById("mq-public-header");
  if (header) {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        header.classList.toggle("is-scrolled", window.scrollY > 4);
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  document.querySelectorAll(".acct-file__input").forEach((input) => {
    const nameEl = input.closest(".acct-file")?.querySelector(".acct-file__name");
    if (!nameEl) return;
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      nameEl.textContent = file ? file.name : "JPG, PNG or WebP";
    });
  });
}

function boot() {
  requestAnimationFrame(initCustomerMotion);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
  boot();
}
