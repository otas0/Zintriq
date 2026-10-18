/**
 * Zintriq marketing interactivity
 * Patterns from 2025–26 product-site research (vanilla, no build):
 * - Magnetic CTAs (Awwwards / SaaS landers)
 * - Pointer spotlight on hero & cards
 * - Hero tile parallax toward cursor
 * - Scroll progress bar
 * - Soft scramble on primitive labels
 * Disabled on touch + prefers-reduced-motion.
 */
(function () {
  "use strict";

  var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var reduce =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!finePointer || reduce) return;

  /* —— Scroll progress —— */
  var bar = document.createElement("div");
  bar.className = "mq-scroll-progress";
  bar.setAttribute("aria-hidden", "true");
  document.body.appendChild(bar);

  function updateProgress() {
    var doc = document.documentElement;
    var max = doc.scrollHeight - window.innerHeight;
    var p = max > 0 ? window.scrollY / max : 0;
    bar.style.width = Math.min(100, Math.max(0, p * 100)).toFixed(2) + "%";
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress, { passive: true });
  updateProgress();

  /* —— Spotlight —— */
  function attachSpotlight(el) {
    if (!el) return;
    el.classList.add("mq-spotlight");
    el.addEventListener("pointermove", function (e) {
      var r = el.getBoundingClientRect();
      var x = ((e.clientX - r.left) / r.width) * 100;
      var y = ((e.clientY - r.top) / r.height) * 100;
      el.style.setProperty("--spot-x", x.toFixed(2) + "%");
      el.style.setProperty("--spot-y", y.toFixed(2) + "%");
      el.classList.add("is-spot-active");
    });
    el.addEventListener("pointerleave", function () {
      el.classList.remove("is-spot-active");
    });
  }

  attachSpotlight(document.querySelector(".zh-hero"));
  attachSpotlight(document.querySelector(".zh-close"));
  document.querySelectorAll(".zm-gallery-card, .zm-price--featured, .zh-template-card").forEach(attachSpotlight);

  /* —— Magnetic buttons —— */
  function attachMagnetic(el, strength) {
    if (!el) return;
    el.classList.add("mq-magnetic");
    var s = strength || 0.28;
    var rect = null;

    function refresh() {
      rect = el.getBoundingClientRect();
    }
    window.addEventListener("resize", refresh, { passive: true });
    window.addEventListener("scroll", refresh, { passive: true });

    el.addEventListener("pointerenter", refresh);
    el.addEventListener("pointermove", function (e) {
      if (!rect) refresh();
      var cx = rect.left + rect.width / 2;
      var cy = rect.top + rect.height / 2;
      var dx = (e.clientX - cx) * s;
      var dy = (e.clientY - cy) * s;
      el.style.setProperty("--mx", dx.toFixed(2) + "px");
      el.style.setProperty("--my", dy.toFixed(2) + "px");
    });
    el.addEventListener("pointerleave", function () {
      el.style.setProperty("--mx", "0px");
      el.style.setProperty("--my", "0px");
    });
  }

  document.querySelectorAll(".mq-public .mq-btn-primary, .zh-hero__actions .mq-btn, .zh-close .mq-btn").forEach(function (btn) {
    attachMagnetic(btn, 0.32);
  });

  /* —— Hero primitive tiles: follow cursor —— */
  var grid = document.querySelector(".zh-hero__grid");
  var hero = document.querySelector(".zh-hero");
  var cells = grid ? Array.prototype.slice.call(grid.querySelectorAll(".zh-hero__cell")) : [];

  if (hero && cells.length) {
    cells.forEach(function (c) {
      c.classList.add("mq-tilt");
    });
    hero.addEventListener("pointermove", function (e) {
      var r = hero.getBoundingClientRect();
      var nx = (e.clientX - r.left) / r.width - 0.5;
      var ny = (e.clientY - r.top) / r.height - 0.5;
      grid.classList.add("is-tracking");
      cells.forEach(function (cell, i) {
        var depth = 6 + (i % 3) * 4;
        var rx = (-ny * depth).toFixed(2);
        var ry = (nx * depth).toFixed(2);
        var tz = (Math.abs(nx) + Math.abs(ny)) * 4;
        cell.style.transform =
          "perspective(700px) rotateX(" + rx + "deg) rotateY(" + ry + "deg) translate3d(" +
          (nx * depth * 0.35).toFixed(2) + "px," + (ny * depth * 0.35).toFixed(2) + "px," +
          tz.toFixed(2) + "px)";
      });
    });
    hero.addEventListener("pointerleave", function () {
      grid.classList.remove("is-tracking");
      cells.forEach(function (cell) {
        cell.style.transform = "";
      });
    });
  }

  /* —— Soft scramble on primitive names —— */
  var glyphs = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  function scramble(el) {
    var original = el.getAttribute("data-label") || el.textContent.trim();
    el.setAttribute("data-label", original);
    el.classList.add("mq-scramble");
    var frames = 8;
    var i = 0;
    var timer = setInterval(function () {
      el.textContent = original
        .split("")
        .map(function (ch, idx) {
          if (ch === " " || i / frames > idx / original.length) return original[idx];
          return glyphs[Math.floor(Math.random() * glyphs.length)];
        })
        .join("");
      i += 1;
      if (i > frames) {
        clearInterval(timer);
        el.textContent = original;
      }
    }, 28);
  }

  document.querySelectorAll(".zh-primitive__name").forEach(function (el) {
    el.addEventListener("pointerenter", function () {
      scramble(el);
    });
  });
})();
