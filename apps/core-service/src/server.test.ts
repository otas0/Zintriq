import { clearAuditLog, getAuditLog } from "@zintriq/extension-host";
import type { BoardConfig, BuildRequest, BuildResult, ExtensionManifest } from "@zintriq/protocol";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { buildApp } from "./server.js";

const validBody = {
  boardId: "esp32",
  entryFile: "main.cpp",
  files: [{ path: "main.cpp", content: "int main(){return 0;}\n" }],
};

describe("core-service", () => {
  const compile = async (request: BuildRequest, _board: BoardConfig): Promise<BuildResult> => {
    const text = request.files.map((file) => file.content).join("\n");
    if (text.includes("syntax error")) {
      return {
        status: "failed",
        diagnostics: [
          { file: "main.cpp", line: 1, column: 5, severity: "error", message: "expected ';'" },
        ],
        durationMs: 4,
      };
    }
    return { status: "success", diagnostics: [], durationMs: 2 };
  };

  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeAll(async () => {
    app = await buildApp({ compile });
  });

  afterAll(async () => {
    await app.close();
  });

  it("returns health ok", async () => {
    const res = await app.inject({ method: "GET", url: "/health" });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { status: string; version: string; uptimeMs: number };
    expect(body.status).toBe("ok");
    expect(body.version).toBe("0.0.0");
    expect(body.uptimeMs).toBeGreaterThanOrEqual(0);
  });

  it("returns fixture boards including community packs", async () => {
    const res = await app.inject({ method: "GET", url: "/boards" });
    expect(res.statusCode).toBe(200);
    const boards = res.json() as BoardConfig[];
    const ids = boards.map((board) => board.id);
    expect(ids).toEqual(expect.arrayContaining(["esp32", "esp32-c3", "rp2040", "stm32", "stm32f103"]));
    expect(boards[0]).toMatchObject({
      name: expect.any(String),
      toolchain: { compiler: expect.any(String), flags: expect.any(Array) },
    });
  });

  it("returns success for a mocked legal build", async () => {
    const res = await app.inject({ method: "POST", url: "/build", payload: validBody });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ status: "success", diagnostics: [], durationMs: 2 });
  });

  it("returns failed with diagnostics for a syntax error", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/build",
      payload: {
        ...validBody,
        files: [{ path: "main.cpp", content: "syntax error\n" }],
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as BuildResult;
    expect(body.status).toBe("failed");
    expect(body.diagnostics.length).toBeGreaterThan(0);
  });

  it("returns 404 BOARD_NOT_FOUND for an unknown board", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/build",
      payload: { ...validBody, boardId: "missing-board" },
    });
    expect(res.statusCode).toBe(404);
    expect(res.json()).toMatchObject({ code: "BOARD_NOT_FOUND" });
  });

  it("returns 400 VALIDATION_ERROR with field paths", async () => {
    const res = await app.inject({ method: "POST", url: "/build", payload: {} });
    expect(res.statusCode).toBe(400);
    const body = res.json() as { code: string; details: { path: string }[] };
    expect(body.code).toBe("VALIDATION_ERROR");
    const paths = body.details.map((item) => item.path);
    expect(paths).toContain("boardId");
    expect(paths).toContain("files");
    expect(paths).toContain("entryFile");
    expect(JSON.stringify(body)).not.toContain("stack");
  });

  it("lists installed extension manifests with extensionsDir", async () => {
    const res = await app.inject({ method: "GET", url: "/extensions" });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { extensions: ExtensionManifest[]; extensionsDir: string };
    expect(body.extensions.map((item) => item.id)).toEqual(["fixture-fs-read", "fixture-no-fs"]);
    expect(body.extensions[0]?.capabilities).toEqual(["fs.read"]);
    expect(body.extensionsDir).toContain("fixtures");
  });

  it("runs a declared extension", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/extensions/fixture-fs-read/run",
      payload: {},
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ ok: true, output: 6 });
  });

  it("returns 403 CAPABILITY_DENIED and an audit record", async () => {
    clearAuditLog();
    const res = await app.inject({
      method: "POST",
      url: "/extensions/fixture-no-fs/run",
      payload: {},
    });
    expect(res.statusCode).toBe(403);
    const body = res.json() as { code: string; details: { capability: string } };
    expect(body.code).toBe("CAPABILITY_DENIED");
    expect(body.details.capability).toBe("fs.read");
    expect(getAuditLog()).toContainEqual(
      expect.objectContaining({
        extensionId: "fixture-no-fs",
        capability: "fs.read",
        action: "denied",
      }),
    );

    const audit = await app.inject({ method: "GET", url: "/audit?limit=10" });
    expect(audit.statusCode).toBe(200);
    const payload = audit.json() as {
      entries: { extensionId: string; capability: string; action: string }[];
      total: number;
      extensionsDir: string;
    };
    expect(payload.total).toBeGreaterThan(0);
    expect(payload.extensionsDir).toBeTruthy();
    expect(payload.entries.some((entry) => entry.extensionId === "fixture-no-fs")).toBe(true);

    const filtered = await app.inject({
      method: "GET",
      url: "/audit?limit=10&extensionId=fixture-no-fs",
    });
    expect(filtered.statusCode).toBe(200);
    const filteredBody = filtered.json() as {
      entries: { extensionId: string }[];
      total: number;
      extensionId: string;
    };
    expect(filteredBody.extensionId).toBe("fixture-no-fs");
    expect(filteredBody.entries.every((entry) => entry.extensionId === "fixture-no-fs")).toBe(true);
    expect(filteredBody.total).toBeGreaterThan(0);

    const empty = await app.inject({
      method: "GET",
      url: "/audit?extensionId=does-not-exist",
    });
    expect(empty.json()).toMatchObject({ total: 0, entries: [] });
  });
});
