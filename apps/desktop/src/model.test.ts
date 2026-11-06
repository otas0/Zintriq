import { describe, expect, it } from "vitest";
import { badgeLabel, planDiagnosticJump } from "./model.js";

describe("badgeLabel", () => {
  it("names the build status", () => {
    expect(badgeLabel("success")).toBe("success");
    expect(badgeLabel("failed")).toBe("failed");
    expect(badgeLabel("idle")).toBe("idle");
  });
});

describe("planDiagnosticJump", () => {
  const files = [{ path: "main.cpp" }, { path: "src/util.cpp" }, { path: "inc/util.h" }];

  it("switches active file when diagnostic is elsewhere", () => {
    const diag = {
      file: "src/util.cpp",
      line: 12,
      column: 3,
      severity: "error",
      message: "expected ';'",
    };
    expect(planDiagnosticJump("main.cpp", files, diag)).toEqual({
      kind: "switch",
      path: "src/util.cpp",
      diag,
    });
  });

  it("stays on the same file when diagnostic matches activePath", () => {
    const diag = {
      file: "main.cpp",
      line: 1,
      column: 1,
      severity: "error",
      message: "oops",
    };
    expect(planDiagnosticJump("main.cpp", files, diag)).toEqual({
      kind: "same",
      path: "main.cpp",
      diag,
    });
  });

  it("falls back to same when diagnostic file is missing", () => {
    const diag = {
      file: "ghost.cpp",
      line: 2,
      column: 1,
      severity: "warning",
      message: "missing",
    };
    expect(planDiagnosticJump("main.cpp", files, diag)).toEqual({
      kind: "same",
      path: "main.cpp",
      diag,
    });
  });
});
