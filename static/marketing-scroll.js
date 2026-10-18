/**
 * Scroll bands + pin/scrub stages (vanilla, no GSAP).
 * - [data-zh-band]: soft progress + step activation
 * - [data-zh-pin]: tall track, sticky viewport, scrubbed stages
 */
(function () {
  "use strict";

  var reduce =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePin =
    window.matchMedia &&
    window.matchMedia("(min-width: 960px)").matches;

  var header = document.getElementById("mq-public-header");
  function headerOffset() {
    return header ? header.getBoundingClientRect().height : 64;
  }

  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  /* —— Soft bands —— */
  var bands = Array.prototype.slice.call(document.querySelectorAll("[data-zh-band]"));

  function bandProgress(el) {
    var rect = el.getBoundingClientRect();
    var vh = window.innerHeight || 1;
    var start = vh * 0.92;
    var end = vh * 0.28;
    var y = rect.top;
    if (rect.bottom < 0 || rect.top > vh) {
      return rect.top > vh ? 0 : 1;
    }
    return clamp(1 - (y - end) / (start - end), 0, 1);
  }

  function updateBandSteps(band, progress) {
    var steps = band.querySelectorAll("[data-zh-step]");
    if (!steps.length) return;
    var n = steps.length;
    var idx = Math.min(n - 1, Math.floor(progress * n));
    var mid = window.innerHeight * 0.45;
    var best = -1;
    var bestDist = Infinity;
    Array.prototype.forEach.call(steps, function (step, i) {
      var r = step.getBoundingClientRect();
      var c = r.top + r.height * 0.35;
      var d = Math.abs(c - mid);
      if (r.bottom > 80 && r.top < window.innerHeight - 40 && d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    if (best < 0) best = idx;
    Array.prototype.forEach.call(steps, function (step, i) {
      step.classList.toggle("is-active", i === best);
      step.classList.toggle("is-passed", i < best);
    });
  }

  /* —— Pin + scrub —— */
  var pins = Array.prototype.slice.call(document.querySelectorAll("[data-zh-pin]"));

  function setupPin(pin) {
    var track = pin.querySelector(".zh-pin__track");
    var stages = Array.prototype.slice.call(pin.querySelectorAll("[data-zh-stage]"));
    var nav = Array.prototype.slice.call(pin.querySelectorAll("[data-zh-stage-nav]"));
    var dotsHost = pin.querySelector(".zh-pin__dots");
    var screens = parseFloat(pin.getAttribute("data-zh-pin-screens") || "3") || 3;
    pin._zh = { track: track, stages: stages, nav: nav, screens: screens, index: -1 };

    if (dotsHost && stages.length) {
      dotsHost.innerHTML = stages
        .map(function (_, i) {
          return '<button type="button" class="zh-pin__dot" data-zh-dot="' + i + '" aria-label="Stage ' + (i + 1) + '"></button>';
        })
        .join("");
      pin._zh.dots = Array.prototype.slice.call(dotsHost.querySelectorAll("[data-zh-dot]"));
      pin._zh.dots.forEach(function (dot) {
        dot.addEventListener("click", function () {
          if (!finePin || reduce) return;
          var i = parseInt(dot.getAttribute("data-zh-dot"), 10);
          var t = pin._zh.track;
          if (!t) return;
          var scrollable = t.offsetHeight - window.innerHeight;
          var start = t.getBoundingClientRect().top + window.scrollY;
          var target = start + (scrollable * (i + 0.5)) / stages.length;
          window.scrollTo({ top: target, behavior: "smooth" });
        });
      });
    }

    nav.forEach(function (item) {
      item.addEventListener("click", function () {
        if (!finePin || reduce) return;
        var i = parseInt(item.getAttribute("data-zh-stage-nav"), 10);
        var t = pin._zh.track;
        if (!t || isNaN(i)) return;
        var scrollable = t.offsetHeight - window.innerHeight;
        var start = t.getBoundingClientRect().top + window.scrollY;
        var target = start + (scrollable * (i + 0.5)) / stages.length;
        window.scrollTo({ top: target, behavior: "smooth" });
      });
    });
  }

  pins.forEach(setupPin);

  function setPinStage(pin, index, progress) {
    var meta = pin._zh;
    if (!meta) return;
    pin.style.setProperty("--zh-pin", progress.toFixed(4));
    pin.classList.toggle("is-pinned", progress > 0 && progress < 1);
    if (index === meta.index) return;
    meta.index = index;
    meta.stages.forEach(function (stage, i) {
      stage.classList.toggle("is-active", i === index);
      stage.classList.toggle("is-passed", i < index);
    });
    if (meta.nav) {
      meta.nav.forEach(function (item, i) {
        item.classList.toggle("is-active", i === index);
        item.classList.toggle("is-passed", i < index);
      });
    }
    if (meta.dots) {
      meta.dots.forEach(function (dot, i) {
        dot.classList.toggle("is-active", i === index);
        dot.classList.toggle("is-passed", i < index);
      });
    }
  }

  function pinProgress(pin) {
    var track = pin._zh && pin._zh.track;
    if (!track) return 0;
    var rect = track.getBoundingClientRect();
    var scrollable = Math.max(1, track.offsetHeight - window.innerHeight);
    var scrolled = -rect.top;
    return clamp(scrolled / scrollable, 0, 1);
  }

  function applyPinHeights() {
    finePin =
      window.matchMedia &&
      window.matchMedia("(min-width: 960px)").matches;
    pins.forEach(function (pin) {
      var track = pin._zh.track;
      if (!track) return;
      if (reduce || !finePin) {
        track.style.height = "";
        pin.classList.add("is-static");
        setPinStage(pin, 0, 1);
        pin._zh.stages.forEach(function (s) {
          s.classList.add("is-active");
          s.classList.remove("is-passed");
        });
        return;
      }
      pin.classList.remove("is-static");
      track.style.height = pin._zh.screens * 100 + "vh";
    });
  }

  var ticking = false;
  function tick() {
    ticking = false;
    document.documentElement.style.setProperty("--header-offset", headerOffset() + "px");

    if (!reduce) {
      bands.forEach(function (band) {
        var p = bandProgress(band);
        band.style.setProperty("--zh-progress", p.toFixed(4));
        band.classList.toggle("is-inview", p > 0.08 && p < 0.98);
        updateBandSteps(band, p);
      });
    }

    if (!reduce && finePin) {
      pins.forEach(function (pin) {
        var p = pinProgress(pin);
        var n = pin._zh.stages.length || 1;
        var idx = Math.min(n - 1, Math.floor(p * n * 0.999));
        setPinStage(pin, idx, p);
      });
    }
  }

  function requestTick() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(tick);
  }

  applyPinHeights();
  if (reduce) {
    pins.forEach(function (pin) {
      pin.classList.add("is-static");
      pin._zh.stages.forEach(function (s) {
        s.classList.add("is-active");
      });
    });
    return;
  }

  window.addEventListener("scroll", requestTick, { passive: true });
  window.addEventListener("resize", function () {
    applyPinHeights();
    requestTick();
  }, { passive: true });
  requestTick();
})();
