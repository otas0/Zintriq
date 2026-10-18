/** How-it-works popup — guests: once per browser; members: first visit (server). */

const GUEST_INTRO_KEY = "mq_hub_intro_v1";

function shouldShowOnboarding(modal) {
  if (!modal || modal.dataset.onboardingOpen !== "1") return false;
  if (modal.dataset.onboardingMode === "guest") {
    try {
      if (localStorage.getItem(GUEST_INTRO_KEY) === "1") return false;
    } catch {
      /* private mode — still show once this session via sessionStorage */
      try {
        if (sessionStorage.getItem(GUEST_INTRO_KEY) === "1") return false;
      } catch {
        /* ignore */
      }
    }
  }
  return true;
}

function markGuestIntroSeen() {
  try {
    localStorage.setItem(GUEST_INTRO_KEY, "1");
  } catch {
    try {
      sessionStorage.setItem(GUEST_INTRO_KEY, "1");
    } catch {
      /* ignore */
    }
  }
  try {
    document.cookie = "mq_hub_intro=1; Path=/; Max-Age=31536000; SameSite=Lax";
  } catch {
    /* ignore */
  }
}

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || "";
}

async function markMemberIntroSeen(modal) {
  if (modal?.dataset.onboardingMode !== "member") return;
  try {
    await fetch("/api/customer/hub-intro-seen", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken(),
        "X-Customer-Auth": "1",
      },
      body: JSON.stringify({ csrf_token: csrfToken() }),
    });
  } catch {
    /* non-blocking */
  }
}

function closeOnboarding(modal) {
  if (!modal || modal.hidden) return;
  if (modal.dataset.closeTimer) {
    window.clearTimeout(Number(modal.dataset.closeTimer));
  }
  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("mq-onboard-open");
  if (modal.dataset.onboardingMode === "guest") markGuestIntroSeen();
  markMemberIntroSeen(modal);
  modal.dataset.closeTimer = String(
    window.setTimeout(() => {
      modal.hidden = true;
      delete modal.dataset.closeTimer;
    }, 300)
  );
}

function openOnboarding(modal) {
  if (!shouldShowOnboarding(modal)) {
    modal.hidden = true;
    return;
  }
  modal.hidden = false;
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("mq-onboard-open");
  requestAnimationFrame(() => {
    requestAnimationFrame(() => modal.classList.add("is-open"));
  });
  modal.querySelector(".mq-onboard__cta")?.focus({ preventScroll: true });
}

function initOnboarding() {
  const modal = document.getElementById("mq-onboard");
  if (!modal) return;

  modal.querySelectorAll("[data-onboard-close]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      closeOnboarding(modal);
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("is-open")) {
      closeOnboarding(modal);
    }
  });

  openOnboarding(modal);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initOnboarding, { once: true });
} else {
  initOnboarding();
}
