/** QR Customer Experience Runtime — session tracking and in-page actions. */

(function () {
  var root = document.querySelector(".qrx-page");
  if (!root || root.dataset.preview === "1") return;

  var runtime = {};
  try {
    runtime = JSON.parse(root.dataset.runtime || "{}");
  } catch (e) {
    return;
  }
  if (!runtime.session_id) return;

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken(),
      },
      credentials: "same-origin",
      body: JSON.stringify(Object.assign({ csrf_token: csrfToken() }, body || {})),
      keepalive: true,
    });
  }

  function track(eventType, detail) {
    postJson(runtime.interact_api, {
      event_type: eventType,
      action_type: detail && detail.actionType,
      action_id: detail && detail.actionId ? Number(detail.actionId) : null,
      metadata: detail && detail.metadata ? detail.metadata : {},
    }).catch(function () {});
  }

  document.querySelectorAll("[data-action-type]").forEach(function (el) {
    el.addEventListener("click", function () {
      track("click", {
        actionType: el.dataset.actionType,
        actionId: el.dataset.actionId,
      });
    });
  });

  var bookingForm = document.getElementById("qrx-booking-form");
  if (bookingForm) {
    bookingForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var fd = new FormData(bookingForm);
      var msg = document.getElementById("qrx-booking-msg");
      postJson(runtime.booking_api, {
        action_id: bookingForm.dataset.actionId || null,
        customer_name: fd.get("customer_name"),
        customer_email: fd.get("customer_email"),
        customer_phone: fd.get("customer_phone"),
        starts_at: fd.get("starts_at"),
        notes: fd.get("notes"),
        title: fd.get("title") || "Booking",
      })
        .then(function (res) {
          if (!res.ok) throw new Error("Booking failed");
          return res.json();
        })
        .then(function () {
          bookingForm.classList.add("hidden");
          if (msg) {
            msg.classList.remove("hidden");
            msg.textContent = "Booking confirmed — we'll see you soon.";
          }
        })
        .catch(function () {
          if (msg) {
            msg.classList.remove("hidden");
            msg.textContent = "Could not create booking. Check your details and try again.";
          }
        });
    });
  }

  var checkinForm = document.getElementById("qrx-checkin-form");
  if (checkinForm) {
    checkinForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var fd = new FormData(checkinForm);
      var msg = document.getElementById("qrx-checkin-msg");
      postJson(runtime.checkin_api, {
        action_id: checkinForm.dataset.actionId || null,
        customer_name: fd.get("customer_name") || "Guest",
      })
        .then(function (res) {
          if (!res.ok) throw new Error("Check-in failed");
          return res.json();
        })
        .then(function () {
          checkinForm.classList.add("hidden");
          if (msg) {
            msg.classList.remove("hidden");
            msg.textContent = "You're checked in. Welcome!";
          }
        })
        .catch(function () {
          if (msg) {
            msg.classList.remove("hidden");
            msg.textContent = "Check-in unavailable — ask staff for help.";
          }
        });
    });
  }
})();
