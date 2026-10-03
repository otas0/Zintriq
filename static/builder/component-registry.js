/** Editor registry cache. The server registry is canonical; these values are offline fallbacks. */

export const COMPONENTS = {
  header: { label: "Header", category: "content", defaults: { title: "", subtitle: "" } },
  text: { label: "Text", category: "content", defaults: { body: "" } },
  image: { label: "Image", category: "media", defaults: { src: "", alt: "" } },
  info: { label: "Information", category: "content", defaults: { title: "", body: "" } },
  actions: { label: "Button", category: "interaction", defaults: { title: "" } },
  shop: { label: "Storefront", category: "commerce", defaults: { label: "View shop", subtitle: "" } },
  survey: { label: "Survey", category: "interaction", defaults: { title: "Your feedback", body: "" } },
  booking: { label: "Booking", category: "interaction", defaults: { title: "Book your visit" } },
  check_in: { label: "Check-in", category: "interaction", defaults: { title: "Confirm your arrival" } },
  contact: { label: "Contact", category: "business", defaults: { title: "Contact", show_store: true } },
};

export const ACTIONS = {
  open_page: { label: "Open Page" },
  start_survey: { label: "Start Survey / Feedback" },
  show_information: { label: "Show Information" },
  create_booking: { label: "Create Booking" },
  start_checkin: { label: "Start Check-in" },
  external_link: { label: "External Link" },
};

const MVP_COMPONENT_IDS = ["text", "header", "image", "actions", "info", "survey"];
const FULL_COMPONENT_IDS = [...MVP_COMPONENT_IDS, "booking", "check_in", "contact", "shop"];
const MVP_ACTION_IDS = ["open_page", "start_survey", "show_information"];
const FULL_ACTION_IDS = [...MVP_ACTION_IDS, "create_booking", "start_checkin", "external_link"];

export const MVP_EDITOR_ADD_OPTIONS = [
  { id: "text", label: "Text" },
  { id: "image", label: "Image" },
  { id: "actions", label: "Button" },
  { id: "survey", label: "Feedback", preset: { title: "Share your feedback", body: "Rate your experience" } },
  { id: "survey", label: "Survey", preset: { title: "Quick survey", body: "Answer a few questions" } },
];

export function componentTypes(includeDeferred = false) {
  return (includeDeferred ? FULL_COMPONENT_IDS : MVP_COMPONENT_IDS)
    .map((id) => ({ id, label: COMPONENTS[id].label }));
}

export function actionTypes(includeDeferred = false) {
  return (includeDeferred ? FULL_ACTION_IDS : MVP_ACTION_IDS)
    .map((id) => ({ id, label: ACTIONS[id].label }));
}

export function componentDefaults(type) {
  return { ...(COMPONENTS[type]?.defaults || COMPONENTS.text.defaults) };
}

export function hydrateComponentRegistry(payload = {}) {
  if (payload.components && typeof payload.components === "object") {
    Object.keys(COMPONENTS).forEach((key) => delete COMPONENTS[key]);
    Object.assign(COMPONENTS, payload.components);
  }
  if (payload.actions && typeof payload.actions === "object") {
    Object.keys(ACTIONS).forEach((key) => delete ACTIONS[key]);
    Object.assign(ACTIONS, payload.actions);
  }
}
