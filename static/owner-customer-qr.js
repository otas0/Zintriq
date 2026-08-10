/** Boot unified customer QR wizard on owner manage pages. */

import { openCustomerQrWizard, maybeOpenCustomerQrWizardFromQuery } from "./customer-qr-wizard.js";

const boot = window.CUSTOMER_QR_BOOT;

function wireAddButton(id, extra = {}) {
  document.getElementById(id)?.addEventListener("click", () => {
    if (!boot?.storeId) return;
    const { onDone: customOnDone, ...wizardOpts } = extra;
    openCustomerQrWizard({
      storeId: boot.storeId,
      storeSlug: boot.storeSlug,
      storeName: boot.storeName,
      ...wizardOpts,
      onDone: customOnDone || (({ redirect }) => {
        if (redirect) window.location.href = redirect;
      }),
    });
  });
}

if (boot?.storeId) {
  wireAddButton("customer-qr-add", boot.shopOnly ? { shopOnly: true } : {});
  wireAddButton("landing-qr-add", {
    landingOnly: true,
    onDone: (result) => {
      if (result.kind === "landing" && result.id && boot.storeSlug) {
        window.location.href = `/manage/${encodeURIComponent(boot.storeSlug)}/landing-qr#builder/${result.id}`;
        return;
      }
      if (result.redirect) window.location.href = result.redirect;
    },
  });
  maybeOpenCustomerQrWizardFromQuery(boot);
}

window.addEventListener("bos:add-customer-qr", (e) => {
  if (!boot?.storeId || e.detail?.storeId !== boot.storeId) return;
  openCustomerQrWizard({
    storeId: boot.storeId,
    storeSlug: boot.storeSlug,
    storeName: boot.storeName,
    landingOnly: Boolean(e.detail?.landingOnly),
    onDone: ({ redirect }) => {
      if (redirect) window.location.href = redirect;
    },
  });
});
