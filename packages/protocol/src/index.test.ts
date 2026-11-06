import { describe, expect, it } from "vitest";
import {
  BoardConfigSchema,
  BuildRequestSchema,
  ExtensionManifestSchema,
  PROTOCOL_VERSION,
  ValidationError,
  validateOrThrow,
} from "./index.js";

describe("protocol schemas", () => {
  it("exports a version", () => {
    expect(PROTOCOL_VERSION).toBe(1);
  });

  it("accepts a valid board config", () => {
    const board = validateOrThrow(BoardConfigSchema, {
      id: "esp32",
      name: "ESP32 DevKit",
      mcuFamily: "esp32",
      toolchain: { compiler: "g++", flags: ["-std=c++17"] },
      pins: { LED: "GPIO2" },
      peripherals: [{ name: "uart0", kind: "uart", pins: ["TX", "RX"] }],
    });
    expect(board.id).toBe("esp32");
  });

  it("rejects unknown board fields", () => {
    expect(() =>
      validateOrThrow(BoardConfigSchema, {
        id: "x",
        name: "X",
        mcuFamily: "esp32",
        toolchain: { compiler: "g++", flags: [] },
        pins: {},
        extra: true,
      }),
    ).toThrow(ValidationError);
  });

  it("rejects a board with no compiler", () => {
    expect(() =>
      validateOrThrow(BoardConfigSchema, {
        id: "x",
        name: "X",
        mcuFamily: "stm32",
        toolchain: { flags: [] },
        pins: {},
      }),
    ).toThrow(ValidationError);
  });

  it("rejects a blank compiler string", () => {
    expect(() =>
      validateOrThrow(BoardConfigSchema, {
        id: "x",
        name: "X",
        mcuFamily: "rp2040",
        toolchain: { compiler: "", flags: [] },
        pins: { LED: "GP25" },
      }),
    ).toThrow(ValidationError);
  });

  it("accepts a build request and extension manifest", () => {
    const req = validateOrThrow(BuildRequestSchema, {
      boardId: "esp32",
      entryFile: "main.cpp",
      files: [{ path: "main.cpp", content: "int main(){}" }],
    });
    expect(req.files).toHaveLength(1);

    const manifest = validateOrThrow(ExtensionManifestSchema, {
      id: "demo",
      name: "Demo",
      version: "0.1.0",
      capabilities: ["fs.read"],
      entryWasm: "demo.wasm",
    });
    expect(manifest.capabilities).toEqual(["fs.read"]);
  });
});
