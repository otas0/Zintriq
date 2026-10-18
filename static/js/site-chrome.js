/** Public chrome: sticky header, mobile menu, theme reveal, language dialog, tabs, scroll reveal. */
(function () {
  "use strict";

  document.documentElement.classList.add("js");
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  window.addEventListener("pageshow", function () {
    if (!window.location.hash) window.scrollTo(0, 0);
  });

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /* —— Scroll reveal: [data-reveal], once; no-JS stays visible via CSS —— */
  (function initReveal() {
    var nodes = document.querySelectorAll("[data-reveal]");
    if (!nodes.length) return;
    var reveal = function (el) {
      el.classList.add("is-revealed");
    };
    if (!("IntersectionObserver" in window)) {
      nodes.forEach(reveal);
      return;
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          reveal(entry.target);
          io.unobserve(entry.target);
        });
      },
      { rootMargin: "0px", threshold: 0 }
    );
    nodes.forEach(function (el, i) {
      el.style.setProperty("--reveal-i", String(i));
      var rect = el.getBoundingClientRect();
      if (rect.top < (window.innerHeight || 0) && rect.bottom > 0) {
        reveal(el);
        return;
      }
      io.observe(el);
    });
  })();

  /* —— Sticky header: border after scroll; do not hide (avoids page slide) —— */
  var header = document.getElementById("mq-public-header");
  if (header) {
    var onScroll = function () {
      var y = window.scrollY || 0;
      header.classList.toggle("is-scrolled", y > 8);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* —— Mobile menu (Popover) —— */
  var menuBtn = document.getElementById("site-menu-btn");
  var menu = document.getElementById("site-menu");
  if (menuBtn && menu) {
    var usePopover = typeof menu.showPopover === "function";
    var menuFocusables = function () {
      return Array.prototype.slice.call(
        menu.querySelectorAll('a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])')
      ).filter(function (el) {
        return !el.hasAttribute("disabled") && el.getClientRects().length > 0;
      });
    };
    var isOpen = function () {
      if (usePopover) return menu.matches(":popover-open");
      return menu.classList.contains("is-open");
    };
    var openMenu = function () {
      if (usePopover) menu.showPopover();
      else {
        menu.hidden = false;
        menu.classList.add("is-open");
      }
      menuBtn.setAttribute("aria-expanded", "true");
      var first = menuFocusables()[0];
      if (first) first.focus();
    };
    var closeMenu = function () {
      if (usePopover) menu.hidePopover();
      else {
        menu.classList.remove("is-open");
        menu.hidden = true;
      }
      menuBtn.setAttribute("aria-expanded", "false");
      menuBtn.focus();
    };
    if (!usePopover) {
      menu.hidden = true;
      menu.classList.add("site-menu--fallback");
    }
    menuBtn.addEventListener("click", function () {
      if (isOpen()) closeMenu();
      else openMenu();
    });
    if (usePopover) {
      menu.addEventListener("toggle", function (ev) {
        var open = ev.newState === "open";
        menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) {
          var first = menuFocusables()[0];
          if (first) first.focus();
        } else {
          menuBtn.focus();
        }
      });
    }
    menu.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") {
        closeMenu();
        return;
      }
      if (ev.key !== "Tab") return;
      var nodes = menuFocusables();
      if (!nodes.length) return;
      var first = nodes[0];
      var last = nodes[nodes.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        ev.preventDefault();
        last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault();
        first.focus();
      }
    });
    menu.querySelectorAll("[data-close-menu]").forEach(function (el) {
      el.addEventListener("click", function () { closeMenu(); });
    });
  }

  /* —— Theme with circular view transition —— */
  var setThemeCore = window.__zintriqSetTheme;
  window.__zintriqSetTheme = function (pref, ev) {
    if (typeof setThemeCore !== "function") return;
    var apply = function () { setThemeCore(pref); };
    var hasPoint = ev && typeof ev.clientX === "number" && typeof ev.clientY === "number";
    var canVt =
      document.startViewTransition &&
      !prefersReducedMotion() &&
      hasPoint;
    if (!canVt) {
      apply();
      return;
    }
    var x = ev.clientX;
    var y = ev.clientY;
    var end = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y)
    );
    document.documentElement.style.setProperty("--vt-x", x + "px");
    document.documentElement.style.setProperty("--vt-y", y + "px");
    document.documentElement.style.setProperty("--vt-r", end + "px");
    document.documentElement.classList.add("is-theme-vt");
    var vt = document.startViewTransition(apply);
    if (vt && vt.finished && typeof vt.finished.finally === "function") {
      vt.finished.finally(function () {
        document.documentElement.classList.remove("is-theme-vt");
      });
    } else {
      document.documentElement.classList.remove("is-theme-vt");
    }
  };

  document.querySelectorAll("[data-theme-set]").forEach(function (btn) {
    btn.addEventListener("click", function (ev) {
      var pref = btn.getAttribute("data-theme-set");
      window.__zintriqSetTheme(pref, ev);
    });
  });
  document.querySelectorAll("[data-theme-cycle]").forEach(function (btn) {
    btn.addEventListener("click", function (ev) {
      var order = ["system", "light", "dark"];
      var cur = document.documentElement.getAttribute("data-theme-pref") || "system";
      var i = order.indexOf(cur);
      var next = order[(i + 1) % order.length];
      window.__zintriqSetTheme(next, ev);
    });
  });

  /* —— Language dialog —— */
  var langOpeners = document.querySelectorAll("[data-lang-open]");
  var langDialog = document.getElementById("lang-dialog");
  if (langDialog) {
    var search = document.getElementById("lang-dialog-search");
    var items = langDialog.querySelectorAll("[data-lang-item]");
    langOpeners.forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (typeof langDialog.showModal === "function") langDialog.showModal();
        if (search) {
          search.value = "";
          items.forEach(function (li) { li.hidden = false; });
          search.focus();
        } else {
          langDialog.focus();
        }
      });
    });
    var closeBtn = document.getElementById("lang-dialog-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () { langDialog.close(); });
    }
    langDialog.addEventListener("click", function (ev) {
      if (ev.target === langDialog) langDialog.close();
    });
    if (search) {
      search.addEventListener("input", function () {
        var q = (search.value || "").trim().toLowerCase();
        items.forEach(function (li) {
          var hay = (li.getAttribute("data-lang-search") || "").toLowerCase();
          li.hidden = q !== "" && hay.indexOf(q) === -1;
        });
      });
    }
  }

  /* —— Tabs (roving tabindex) —— */
  document.querySelectorAll("[data-tabs]").forEach(function (root) {
    var tabs = Array.prototype.slice.call(root.querySelectorAll('[role="tab"]'));
    var panels = Array.prototype.slice.call(root.querySelectorAll('[role="tabpanel"]'));
    if (!tabs.length) return;
    function select(i) {
      tabs.forEach(function (tab, idx) {
        var on = idx === i;
        tab.setAttribute("aria-selected", on ? "true" : "false");
        tab.tabIndex = on ? 0 : -1;
        var panel = panels[idx];
        if (panel) panel.hidden = !on;
      });
      tabs[i].focus();
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { select(i); });
      tab.addEventListener("keydown", function (ev) {
        var next = i;
        if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
          ev.preventDefault();
          var dir = ev.key === "ArrowRight" ? 1 : -1;
          if (document.documentElement.getAttribute("dir") === "rtl") dir *= -1;
          next = (i + dir + tabs.length) % tabs.length;
          select(next);
        } else if (ev.key === "Home") {
          ev.preventDefault();
          select(0);
        } else if (ev.key === "End") {
          ev.preventDefault();
          select(tabs.length - 1);
        }
      });
    });
  });

  /* Region hint (from prior shell) */
  var hint = document.getElementById("mq-region-hint");
  if (hint) {
    var cookieName = hint.getAttribute("data-dismiss-cookie") || "mq_region_hint_dismiss";
    var dismissKey = hint.getAttribute("data-dismiss-key") || "";
    function dismissHint() {
      if (dismissKey) {
        document.cookie =
          cookieName +
          "=" +
          encodeURIComponent(dismissKey) +
          "; Path=/; Max-Age=" +
          60 * 60 * 24 * 90 +
          "; SameSite=Lax";
      }
      hint.remove();
    }
    var closeBtn = document.getElementById("mq-region-hint-close");
    var stayBtn = document.getElementById("mq-region-hint-stay");
    if (closeBtn) closeBtn.addEventListener("click", dismissHint);
    if (stayBtn) stayBtn.addEventListener("click", dismissHint);
  }

  /* Portal plugins: copy sha256 for desktop Open verify */
  var toastEscBound = false;
  var toastTimer = 0;
  var toastTick = 0;
  var TOAST_MS = 2200;
  function dismissCopyToast() {
    if (toastTimer) {
      window.clearTimeout(toastTimer);
      toastTimer = 0;
    }
    if (toastTick) {
      window.clearInterval(toastTick);
      toastTick = 0;
    }
    var existing = document.querySelector(".mq-toast");
    if (existing) existing.remove();
  }
  function showCopyToast(message) {
    if (prefersReducedMotion()) return;
    dismissCopyToast();
    var toast = document.createElement("div");
    toast.className = "mq-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("tabindex", "0");
    toast.title = "Short-press or Esc to dismiss";
    var label = document.createElement("span");
    label.className = "mq-toast__msg";
    label.textContent = message || "Copied — paste when Studio Open verifies";
    var countdown = document.createElement("span");
    countdown.className = "mq-toast__secs";
    countdown.setAttribute("data-toast-secs", "1");
    toast.appendChild(label);
    toast.appendChild(document.createTextNode(" "));
    toast.appendChild(countdown);
    var started = Date.now();
    function paintSecs() {
      if (!toast.parentNode) return;
      var left = Math.max(0, TOAST_MS - (Date.now() - started));
      var secs = (left / 1000).toFixed(1);
      countdown.textContent = secs + "s";
    }
    paintSecs();
    var pressAt = 0;
    toast.addEventListener("pointerdown", function (ev) {
      if (ev.target && ev.target.closest && ev.target.closest("[data-copy-sha256]")) return;
      pressAt = Date.now();
    });
    toast.addEventListener("pointerup", function (ev) {
      if (!pressAt) return;
      var held = Date.now() - pressAt;
      pressAt = 0;
      /* Short press closes; does not reset remaining countdown. */
      if (held > 0 && held < 350) {
        ev.preventDefault();
        dismissCopyToast();
      }
    });
    toast.addEventListener("pointercancel", function () {
      pressAt = 0;
    });
    document.body.appendChild(toast);
    if (!toastEscBound) {
      toastEscBound = true;
      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape" && document.querySelector(".mq-toast")) {
          ev.preventDefault();
          dismissCopyToast();
        }
      });
    }
    toastTick = window.setInterval(paintSecs, 100);
    toastTimer = window.setTimeout(function () {
      toastTimer = 0;
      if (toastTick) {
        window.clearInterval(toastTick);
        toastTick = 0;
      }
      if (toast.parentNode) toast.remove();
    }, TOAST_MS);
  }

  document.querySelectorAll("[data-copy-sha256]").forEach(function (button) {
    button.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var value = button.getAttribute("data-copy-sha256") || "";
      if (!value) return;
      var label = button.textContent;
      var done = function () {
        button.textContent = button.getAttribute("data-copied-label") || "Copied";
        showCopyToast("Copied sha256 — paste when Studio Open verifies");
        window.setTimeout(function () {
          button.textContent = label;
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).then(done).catch(function () {
          window.prompt("sha256", value);
        });
      } else {
        window.prompt("sha256", value);
      }
    });
  });
})();
