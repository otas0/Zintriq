/** Owner-facing customer QR types (Restaurant, Clinic, etc.). */

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
