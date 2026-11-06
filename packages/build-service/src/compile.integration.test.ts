import { spawnSync } from "node:child_process";
import type { BoardConfig, BuildRequest } from "@zintriq/protocol";
import { describe, expect, it } from "vitest";
import { compileCheck } from "./compile.js";

const gpp = spawnSync("g++", ["--version"], { encoding: "utf8" });
const hasGpp = gpp.status === 0;

const board: BoardConfig = {
  id: "esp32",
  name: "ESP32",
  mcuFamily: "esp32",
  toolchain: { compiler: "g++", flags: ["-std=c++17", "-fsyntax-only"] },
  pins: {},
  peripherals: [],
};

describe.skipIf(!hasGpp)("compileCheck integration", () => {
  it("compiles a valid C++ snippet", async () => {
    const request: BuildRequest = {
      boardId: "esp32",
      entryFile: "main.cpp",
      files: [{ path: "main.cpp", content: "int main(){return 0;}\n" }],
    };
    const result = await compileCheck(request, board);
    expect(result.status).toBe("success");
  });

  it("reports a line and column for invalid C++", async () => {
    const request: BuildRequest = {
      boardId: "esp32",
      entryFile: "main.cpp",
      files: [{ path: "main.cpp", content: "int main(){ return }\n" }],
    };
    const result = await compileCheck(request, board);
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]?.line).toBeGreaterThan(0);
    expect(result.diagnostics[0]?.column).toBeGreaterThan(0);
  });
});
