import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";
import { CapabilityDeniedError, clearAuditLog, getAuditLog, runExtension } from "./index.js";

const fixtures = fileURLToPath(new URL("../../../fixtures/extensions", import.meta.url));

function loadManifest(name: string) {
  return JSON.parse(readFileSync(join(fixtures, name), "utf8")) as unknown;
}

describe("runExtension", () => {
  beforeEach(() => {
    clearAuditLog();
  });

  it("reads an allowed path when fs.read is declared", async () => {
    const result = await runExtension(loadManifest("manifest-declared.json"), 0, 2_000, 16);
    expect(result.ok).toBe(true);
    expect(result.output).toBe(readFileSync(join(fixtures, "allowed.txt")).length);
  });

  it("denies fs.read when the manifest declares no capabilities", async () => {
    await expect(runExtension(loadManifest("manifest-undeclared.json"), 0, 2_000, 16)).rejects.toBeInstanceOf(
      CapabilityDeniedError,
    );
    const denied = getAuditLog().find((entry) => entry.action === "denied");
    expect(denied).toMatchObject({
      extensionId: "fixture-no-fs",
      capability: "fs.read",
      action: "denied",
    });
    expect(denied?.timestamp).toBeTruthy();
  });

  it("returns EXTENSION_TIMEOUT when the guest does not finish", async () => {
    const result = await runExtension(loadManifest("manifest-declared.json"), 1, 200, 16);
    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("EXTENSION_TIMEOUT");
  });

  it("returns EXTENSION_OOM when the guest grows past the limit", async () => {
    const result = await runExtension(loadManifest("manifest-declared.json"), 2, 2_000, 1);
    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("EXTENSION_OOM");
  });

  it("rejects a manifest with an unknown field or a missing capabilities list", async () => {
    const declared = loadManifest("manifest-declared.json") as Record<string, unknown>;
    await expect(runExtension({ ...declared, extra: true }, 0, 1_000, 16)).rejects.toThrow(/manifest/);
    const { capabilities: _ignored, ...missing } = declared;
    await expect(runExtension(missing, 0, 1_000, 16)).rejects.toThrow(/capabilities/);
  });

  it("rejects an unknown capability name", async () => {
    const declared = loadManifest("manifest-declared.json") as Record<string, unknown>;
    await expect(
      runExtension({ ...declared, capabilities: ["shell"] }, 0, 1_000, 16),
    ).rejects.toThrow(/manifest/);
  });
});
