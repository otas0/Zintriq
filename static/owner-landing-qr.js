/** Landing QR builder — embedded in store manage context. */

import { mountQrExperiencesPage } from "./bos/features/qr-experiences-page.js";

const boot = window.LANDING_QR_BOOT;
const root = document.getElementById("landing-qr-root");

if (root && boot?.storeId) {
  mountQrExperiencesPage(root, { embedded: true, storeId: boot.storeId });
}
