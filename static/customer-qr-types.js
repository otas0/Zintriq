/** Unified customer QR entry types — shop, landing, and specialized. */

export const CUSTOMER_QR_TYPES = [
  {
    id: "restaurant",
    template_id: "restaurant",
    name: "Restaurant",
    description: "Table QR — menu, booking, and feedback for diners.",
  },
  {
    id: "clinic",
    template_id: "service",
    name: "Clinic",
    description: "Appointments, arrival check-in, and patient feedback.",
  },
  {
    id: "information",
    template_id: "product",
    name: "Information",
    description: "Share business info, product details, or menu content.",
  },
  {
    id: "feedback",
    template_id: "feedback_only",
    name: "Feedback",
    description: "Let customers leave a quick rating and comment.",
  },
  {
    id: "survey",
    template_id: "product",
    name: "Survey",
    description: "Collect structured survey answers after a scan.",
  },
];

export const SHOP_QR_ENTRY = {
  id: "shop",
  section: "shop",
  name: "Shop QR",
  description: "Scan opens your menu and storefront directly.",
  defaultName: "Counter",
  kind: "shop",
};

export const SPECIALIZED_QR_ENTRIES = [
  {
    id: "product",
    section: "specialized",
    name: "Product QR",
    description: "Detailed product page with specs and downloads.",
    defaultName: "New product",
    kind: "product",
  },
  {
    id: "event",
    section: "specialized",
    name: "Event Pass",
    description: "Tickets and attendee check-in for an event.",
    defaultName: "New event",
    kind: "event",
  },
  {
    id: "business_card",
    section: "specialized",
    name: "Business Card",
    description: "Digital contact card for a team member.",
    defaultName: "New card",
    kind: "business_card",
  },
  {
    id: "check_in",
    section: "specialized",
    name: "Check-in",
    description: "Visitor or staff check-in at a location.",
    defaultName: "Front desk",
    kind: "check_in",
  },
];

/** @returns {Array<{ id: string, section: string, name: string, description: string, defaultName: string, kind: string, template_id?: string, landingType?: string }>} */
export function allCustomerQrEntries({ landingOnly = false, shopOnly = false } = {}) {
  const landing = CUSTOMER_QR_TYPES.map((t) => ({
    id: `landing_${t.id}`,
    section: "landing",
    name: t.name,
    description: t.description,
    defaultName: t.name,
    kind: "landing",
    landingType: t.id,
    template_id: t.template_id,
  }));
  if (landingOnly) return landing;
  if (shopOnly) return [SHOP_QR_ENTRY];
  return [SHOP_QR_ENTRY, ...landing, ...SPECIALIZED_QR_ENTRIES];
}
