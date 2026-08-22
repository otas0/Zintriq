/** How-it-works popup — guests: every Home visit; members: first visit (server-tracked). */

function shouldShowOnboarding(modal) {
  return modal?.dataset.onboardingOpen === "1";
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
