import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("node:child_process", () => ({
  spawnSync: vi.fn(),
}));

import { spawnSync } from "node:child_process";
import { detectLanguageServers } from "./detect.js";

const spawn = vi.mocked(spawnSync);

afterEach(() => {
  spawn.mockReset();
});

describe("detectLanguageServers", () => {
  it("marks clangd and pylsp available when --version exits 0", () => {
    spawn.mockImplementation((command) => {
      if (command === "clangd") {
        return { status: 0, stdout: "clangd version 18\n", stderr: "", error: undefined } as never;
      }
      return { status: 0, stdout: "pylsp 1.0\n", stderr: "", error: undefined } as never;
    });
    const found = detectLanguageServers();
    expect(found.every((item) => item.available)).toBe(true);
  });

  it("marks missing binaries as unavailable", () => {
    spawn.mockImplementation(() => {
      const err = Object.assign(new Error("spawn ENOENT"), { code: "ENOENT" });
      return { status: null, stdout: "", stderr: "", error: err } as never;
    });
    const found = detectLanguageServers();
    expect(found.every((item) => !item.available)).toBe(true);
    expect(found[0]?.detail).toContain("not found");
  });
});
