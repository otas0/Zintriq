import { defineConfig } from "@playwright/test";
import { E2E_UI_PORT, E2E_UI_URL } from "./e2e/ui-url.mjs";

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    trace: "retain-on-failure",
    baseURL: E2E_UI_URL,
  },
  webServer: {
    command: `corepack pnpm exec vite --host localhost --port ${E2E_UI_PORT} --strictPort`,
    url: E2E_UI_URL,
    // Never reuse an unrelated process that happens to listen on this port.
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
