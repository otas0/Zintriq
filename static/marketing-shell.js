/** Public shell — header scroll + mobile nav (shared by all product pages). */
(function () {
  "use strict";

  var header = document.getElementById("mq-public-header");
  if (header) {
    var onScroll = function () {
      header.classList.toggle("is-scrolled", window.scrollY > 8);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  var menuBtn = document.getElementById("mq-menu-toggle");
  var mobileNav = document.getElementById("mq-mobile-nav");
  if (menuBtn && mobileNav) {
    menuBtn.addEventListener("click", function () {
      var open = mobileNav.classList.toggle("is-open");
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
      var closeLabel = menuBtn.getAttribute("data-label-close");
      var openLabel = menuBtn.getAttribute("data-label-open");
      menuBtn.setAttribute("aria-label", open && closeLabel ? closeLabel : openLabel || menuBtn.getAttribute("aria-label"));
    });
  }

  var hint = document.getElementById("mq-region-hint");
  if (hint) {
    var cookieName = hint.getAttribute("data-dismiss-cookie") || "mq_region_hint_dismiss";
    var dismissKey = hint.getAttribute("data-dismiss-key") || "";

    function dismissHint() {
      if (dismissKey) {
        var maxAge = 60 * 60 * 24 * 90;
        document.cookie =
          cookieName +
          "=" +
          encodeURIComponent(dismissKey) +
          "; Path=/; Max-Age=" +
          maxAge +
          "; SameSite=Lax";
      }
      hint.remove();
    }

    var closeBtn = document.getElementById("mq-region-hint-close");
    var stayBtn = document.getElementById("mq-region-hint-stay");
    if (closeBtn) closeBtn.addEventListener("click", dismissHint);
    if (stayBtn) stayBtn.addEventListener("click", dismissHint);
  }
})();
