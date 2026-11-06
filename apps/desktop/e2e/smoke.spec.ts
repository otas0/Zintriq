import { _electron as electron, expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const electronBin = path.resolve(
  here,
  "../../../desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron",
);

const extensions = [
  {
    id: "reader",
    name: "Reader",
    version: "0.1.0",
    capabilities: ["fs.read"],
    entryWasm: "fixture.wasm",
  },
  {
    id: "locked",
    name: "Locked",
    version: "0.1.0",
    capabilities: [],
    entryWasm: "fixture.wasm",
  },
];

const boards = [
  { id: "esp32", name: "ESP32", mcuFamily: "esp32" },
  { id: "rp2040", name: "RP2040", mcuFamily: "rp2040" },
  { id: "stm32", name: "STM32", mcuFamily: "stm32" },
];

test("editor, board select, LSP mock, and capability deny", async () => {
  const app = await electron.launch({
    executablePath: electronBin,
    args: [path.join(here, "electron-main.cjs")],
    env: {
      ...process.env,
      ZINTRIQ_UI_URL: "http://localhost:5173",
    },
  });
  const page = await app.firstWindow();
  await page.route("http://127.0.0.1:4317/**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "GET" && url.pathname === "/health") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", version: "0.0.0", uptimeMs: 10 }),
      });
      return;
    }
    if (route.request().method() === "GET" && url.pathname === "/boards") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(boards),
      });
      return;
    }
    if (route.request().method() === "GET" && url.pathname === "/extensions") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ extensions, extensionsDir: "/tmp/fixtures/extensions" }),
      });
      return;
    }
    if (route.request().method() === "GET" && url.pathname === "/audit") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ entries: [], total: 0, extensionsDir: "/tmp/fixtures/extensions" }),
      });
      return;
    }
    if (route.request().method() === "POST" && url.pathname === "/extensions/reader/run") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, output: 6, durationMs: 3 }),
      });
      return;
    }
    if (route.request().method() === "POST" && url.pathname === "/extensions/locked/run") {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({
          code: "CAPABILITY_DENIED",
          message: "capability denied: fs.read",
          details: { capability: "fs.read" },
        }),
      });
      return;
    }
    if (route.request().method() === "POST" && url.pathname === "/build") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "success", diagnostics: [], durationMs: 12 }),
      });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ code: "NOT_FOUND", message: "not found" }),
    });
  });
  await page.reload();
  await expect(page.locator(".monaco-editor")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByLabel("开发板").locator("option")).toHaveCount(3);
  await page.getByRole("button", { name: "构建检查" }).click();
  await expect(page.getByTestId("build-badge")).toHaveText(/success|failed/);
  await expect(page.getByTestId("build-duration")).toHaveText("12 ms");
  await expect(page.getByTestId("extension-card")).toHaveCount(2);
  await expect(page.getByTestId("extensions-dir")).toContainText("fixtures/extensions");

  await page.getByTestId("connect-lsp").click();
  await expect(page.getByTestId("lsp-status")).toHaveText("mock");
  await expect(page.getByRole("status").filter({ hasText: "mock LSP" })).toBeVisible();

  await page.getByRole("button", { name: "运行 Reader" }).click();
  await expect(page.getByTestId("extension-output")).toHaveText("6");
  await page.getByRole("button", { name: "运行 Locked" }).click();
  await expect(page.getByTestId("extension-output")).toHaveText("扩展未声明该能力");
  await app.close();
});
