/** Business OS Event Bus — client-side domain event backbone. */

/** @typedef {{ event_type: string, object_type: string, object_id: number|string, title?: string, detail?: string, metadata?: object, href?: string, created_at?: string }} DomainEventDetail */

/** @type {Map<string, Set<(event: DomainEventDetail) => void>>} */
const handlers = new Map();

/** @type {DomainEventDetail[]} */
let serverEvents = [];

/** @param {string} pattern Event type or prefix (e.g. "feedback." or "customer.created") */
export function on(pattern, handler) {
  if (!handlers.has(pattern)) handlers.set(pattern, new Set());
  handlers.get(pattern).add(handler);
  return () => handlers.get(pattern)?.delete(handler);
}

/** @param {DomainEventDetail} event */
export function emit(event) {
  serverEvents.unshift(event);
  if (serverEvents.length > 200) serverEvents.length = 200;

  window.dispatchEvent(new CustomEvent("bos:domain-event", { detail: event }));

  handlers.forEach((set, pattern) => {
    if (event.event_type === pattern || event.event_type.startsWith(pattern)) {
      set.forEach((fn) => fn(event));
    }
  });
}

export function getRecentEvents(limit = 50) {
  return serverEvents.slice(0, limit);
}

/** Pull workspace events from server and fan-out to subscribers. */
export async function syncServerEvents(workspaceId) {
  if (!workspaceId) return [];
  try {
    const res = await fetch(
      `/api/events?workspace_id=${encodeURIComponent(workspaceId)}&limit=30`,
      { credentials: "same-origin" },
    );
    if (!res.ok) return [];
    const events = await res.json();
    events.forEach((e) => {
      if (!serverEvents.some((s) => s.event_id === e.event_id)) {
        emit(e);
      }
    });
    return events;
  } catch {
    return [];
  }
}

/** @param {import('../services/workspace-context.js').getActiveWorkspaceId} getWsId */
export function initEventBus(getActiveWorkspaceId) {
  on("feedback.submitted", (event) => {
    import("./notifications.js").then(({ handleDomainEventNotification }) => {
      handleDomainEventNotification(event);
    });
  });
  on("customer.", (event) => {
    import("./notifications.js").then(({ handleDomainEventNotification }) => {
      handleDomainEventNotification(event);
    });
  });

  const wsId = getActiveWorkspaceId?.();
  const deferSync = () => {
    if (wsId) syncServerEvents(wsId);
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(deferSync, { timeout: 3000 });
  } else {
    setTimeout(deferSync, 800);
  }

  window.addEventListener("bos:workspace-changed", async () => {
    const id = getActiveWorkspaceId?.();
    if (id) await syncServerEvents(id);
  });

  // Poll for new server events every 60s
  setInterval(() => {
    const id = getActiveWorkspaceId?.();
    if (id) syncServerEvents(id);
  }, 60000);
}
