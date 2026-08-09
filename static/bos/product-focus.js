/**
 * Business OS MVP — product scope & navigation.
 * Store · Team · Settings
 */

/** @typedef {{ id: string, label: string, icon: string, path: string, external?: boolean, hidden?: boolean, group?: string }} NavItem */

/** MVP feature flags — defer complexity until core QR is stable. */
export const MVP_FLAGS = {
  /** Booking, check-in, event actions — backend kept, UI hidden. */
  deferredActions: false,
  /** Visual workflow engine — use simple block/action config instead. */
  workflowEngine: false,
  /** Customer CRM / interaction profiles — use response history instead. */
  customerCrm: false,
  /** Analytics dashboards beyond views + response counts. */
  advancedAnalytics: false,
  /** Plugin marketplace & external integrations. */
  plugins: false,
  reputationPlugins: false,
  googleCalendarSync: false,
  connectedApps: false,
  /** Settings → Integrations section (placeholder cards only). */
  integrationsPlaceholder: true,
  showCalendarNav: false,
  showOperationsNav: false,
};

/** MVP team roles shown in UI (maps to DB via normalize_mvp_role). */
export const MVP_TEAM_ROLES = [
  { id: "admin", label: "Admin", db: "administrator" },
  { id: "member", label: "Member", db: "member" },
];

/** @deprecated use MVP_FLAGS */
export const PRODUCT_FLAGS = MVP_FLAGS;

/** @type {readonly NavItem[]} */
export const PRODUCT_NAV = [
  { id: "store", label: "Stores", icon: "▣", path: "/app/store", group: "core" },
  { id: "team", label: "Team", icon: "◈", path: "/app/team", group: "team" },
  { id: "settings", label: "Settings", icon: "⚙", path: "/app/settings", group: "settings" },
  /* Legacy — redirect to Store tabs */
  { id: "qr", label: "Experiences", icon: "⬡", path: "/app/store#experiences", group: "legacy", hidden: true },
  { id: "responses", label: "Responses", icon: "✎", path: "/app/store#responses", group: "legacy", hidden: true },
  { id: "customers", label: "Customers", icon: "★", path: "/app/store#responses", group: "legacy", hidden: true },
  { id: "interactions", label: "Interactions", icon: "↔", path: "/app/store#responses", group: "legacy", hidden: true },
  { id: "feedback", label: "Feedback", icon: "★", path: "/app/store#responses", group: "legacy", hidden: true },
  { id: "booking", label: "Booking", icon: "◷", path: "/app/booking", group: "legacy", hidden: true },
  { id: "calendar", label: "Calendar", icon: "📅", path: "/app/calendar", group: "legacy", hidden: true },
];

export function visibleNav() {
  return PRODUCT_NAV.filter((n) => !n.hidden);
}

/** @type {readonly { label: string, action: string, path?: string, href?: string }[]} */
export const PRODUCT_CREATE_ITEMS = [
  { label: "Add customer QR", action: "nav", path: "/app/store#experiences" },
];
