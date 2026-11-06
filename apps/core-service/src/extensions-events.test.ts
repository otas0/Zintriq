import { mkdirSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { createConnection } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { buildApp } from "./server.js";

const dir = join(tmpdir(), `zintriq-ext-events-${Date.now()}`);

function writeManifest(id: string) {
  writeFileSync(
    join(dir, `${id}.json`),
    JSON.stringify({
      id,
      name: id,
      version: "0.0.1",
      capabilities: [],
      entryWasm: "fixture.wasm",
    }),
    "utf8",
  );
}

function waitForExtensionChange(
  baseUrl: string,
  trigger: () => void,
): Promise<{ added: string[]; removed: string[] }> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("SSE timeout")), 8_000);
    const url = new URL("/extensions/events", baseUrl);
    const socket = createConnection({ host: url.hostname, port: Number(url.port) }, () => {
      socket.write(`GET ${url.pathname} HTTP/1.1\r\nHost: ${url.host}\r\nAccept: text/event-stream\r\n\r\n`);
    });
    let buffer = "";
    let triggered = false;
    socket.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      if (buffer.includes('"type":"connected"') && !triggered) {
        triggered = true;
        trigger();
      }
      const match = /data: ({"type":"extensions-changed"[^\n]+})\n/.exec(buffer);
      if (match?.[1]) {
        clearTimeout(timer);
        const payload = JSON.parse(match[1]) as { added: string[]; removed: string[] };
        socket.destroy();
        resolve(payload);
      }
    });
    socket.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

describe("GET /extensions/events diff", () => {
  let app: Awaited<ReturnType<typeof buildApp>>;
  let baseUrl = "";

  beforeAll(async () => {
    mkdirSync(dir, { recursive: true });
    writeManifest("alpha");
    app = await buildApp({
      extensionsDir: dir,
      compile: async () => ({ status: "success", diagnostics: [], durationMs: 1 }),
    });
    await app.listen({ host: "127.0.0.1", port: 0 });
    const address = app.server.address();
    if (!address || typeof address === "string") {
      throw new Error("expected TCP address");
    }
    baseUrl = `http://127.0.0.1:${address.port}`;
  });

  afterAll(async () => {
    await app.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("emits added when a temporary manifest appears", async () => {
    const payload = await waitForExtensionChange(baseUrl, () => writeManifest("beta"));
    expect(payload.added).toContain("beta");
    expect(payload.removed).toEqual([]);
  });

  it("emits removed when a temporary manifest disappears", async () => {
    const payload = await waitForExtensionChange(baseUrl, () => {
      unlinkSync(join(dir, "beta.json"));
    });
    expect(payload.removed).toContain("beta");
    expect(payload.added).toEqual([]);
  });
});
