/** Marketing page motion / reveal — shell chrome lives in marketing-shell.js. */
(function () {
  "use strict";

  var reduce =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var mobileNav = document.getElementById("mq-mobile-nav");

  function markReveal(el, delay) {
    if (!el || el.classList.contains("mq-reveal")) return;
    el.classList.add("mq-reveal");
    if (delay) el.style.setProperty("--reveal-delay", delay + "ms");
  }

  function preparePage() {
    document.querySelectorAll(".zh-proof, .zh-section").forEach(function (el, i) {
      markReveal(el, Math.min(i * 40, 160));
    });

    document.querySelectorAll(".zm-page > section, .zm-gallery-card, .zm-price, .zm-primitive-block").forEach(function (el, i) {
      markReveal(el, Math.min((i % 6) * 50, 200));
    });

    document.querySelectorAll(".zh-steps:not(.zh-steps--scrub), .zh-primitive-list:not(.zh-primitive-list--scrub), .zh-entry-row, .zh-template-row, .zm-gallery, .zm-price-grid, .zh-trust").forEach(function (group) {
      if (group.closest("[data-zh-band]") && group.querySelector("[data-zh-step]")) return;
      group.classList.add("mq-reveal-stagger");
      markReveal(group, 0);
      Array.prototype.forEach.call(group.children, function (child, idx) {
        child.classList.add("mq-reveal-child");
        child.style.setProperty("--stagger-delay", idx * 70 + "ms");
      });
    });

    var grid = document.querySelector(".zh-hero__grid");
    if (grid) {
      requestAnimationFrame(function () {
        grid.classList.add("is-alive");
      });
    }
  }

  function revealAll() {
    document.querySelectorAll(".mq-reveal").forEach(function (el) {
      el.classList.add("is-visible");
    });
  }

  preparePage();

  if (reduce) {
    revealAll();
  } else if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    document.querySelectorAll(".mq-reveal").forEach(function (el) {
      observer.observe(el);
    });
  } else {
    revealAll();
  }

  document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener("click", function (e) {
      var id = link.getAttribute("href");
      if (!id || id.length <= 1) return;
      var target = document.querySelector(id);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({
        behavior: reduce ? "auto" : "smooth",
        block: "start",
      });
      if (mobileNav) mobileNav.classList.remove("is-open");
    });
  });
})();
