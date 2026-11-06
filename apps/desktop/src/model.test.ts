import { describe, expect, it } from "vitest";
import { badgeLabel } from "./model.js";

describe("badgeLabel", () => {
  it("names the build status", () => {
    expect(badgeLabel("success")).toBe("success");
    expect(badgeLabel("failed")).toBe("failed");
    expect(badgeLabel("idle")).toBe("idle");
  });
});
