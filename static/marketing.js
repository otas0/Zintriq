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
    });
  }

  if ("IntersectionObserver" in window) {
    document.querySelectorAll(".mq-reveal").forEach(function (el) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.1, rootMargin: "0px 0px -24px 0px" }
      );
      observer.observe(el);
    });
  } else {
    document.querySelectorAll(".mq-reveal").forEach(function (el) {
      el.classList.add("is-visible");
    });
  }

  document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener("click", function (e) {
      var id = link.getAttribute("href");
      if (id.length <= 1) return;
      var target = document.querySelector(id);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        if (mobileNav) mobileNav.classList.remove("is-open");
      }
    });
  });
})();
