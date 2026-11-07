import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  findPinConflicts,
  HalRegistry,
  HalRegistryError,
  loadBoardFromYaml,
  parseBoardConfig,
} from "./index.js";

const validYaml = `
id: esp32
name: ESP32 DevKitC
mcuFamily: esp32
toolchain:
  compiler: g++
  flags: ["-std=c++17"]
pins:
  LED: GPIO2
peripherals: []
`;

describe("hal-registry", () => {
  it("loads the three fixture boards", () => {
    const registry = HalRegistry.fromDir();
    const ids = registry.listBoards().map((b) => b.id);
    expect(ids).toEqual(["esp32", "esp32-c3", "esp32-s3", "rp2040", "stm32", "stm32f103"]);
    expect(registry.getBoard("stm32").mcuFamily).toBe("stm32");
  });

  it("accepts a legal board config", () => {
    const board = loadBoardFromYaml(validYaml);
    expect(board.toolchain.compiler).toBe("g++");
    expect(findPinConflicts(board.pins)).toEqual([]);
  });

  it("rejects unknown fields", () => {
    expect(() =>
      parseBoardConfig({
        id: "x",
        name: "X",
        mcuFamily: "esp32",
        toolchain: { compiler: "g++", flags: [] },
        pins: { LED: "GPIO2" },
        mystery: 1,
      }),
    ).toThrow(HalRegistryError);
  });

  it("rejects missing toolchain compiler", () => {
    expect(() =>
      parseBoardConfig({
        id: "x",
        name: "X",
        mcuFamily: "esp32",
        pins: {},
      }),
    ).toThrow(HalRegistryError);

    try {
      parseBoardConfig({
        id: "x",
        name: "X",
        mcuFamily: "esp32",
        toolchain: { compiler: "   ", flags: [] },
        pins: {},
      });
      expect.fail("expected missing toolchain");
    } catch (err) {
      expect(err).toBeInstanceOf(HalRegistryError);
      expect((err as HalRegistryError).code).toBe("missing_toolchain");
    }
  });

  it("rejects pin conflicts", () => {
    expect(() =>
      parseBoardConfig({
        id: "x",
        name: "X",
        mcuFamily: "rp2040",
        toolchain: { compiler: "g++", flags: [] },
        pins: { LED: "GP25", STATUS: "GP25" },
      }),
    ).toThrow(HalRegistryError);

    try {
      parseBoardConfig({
        id: "x",
        name: "X",
        mcuFamily: "rp2040",
        toolchain: { compiler: "g++", flags: [] },
        pins: { LED: "GP25", STATUS: "GP25" },
      });
      expect.fail("expected pin conflict");
    } catch (err) {
      expect(err).toBeInstanceOf(HalRegistryError);
      expect((err as HalRegistryError).code).toBe("pin_conflict");
    }
  });

  it("loads boards from a custom directory", () => {
    const dir = mkdtempSync(join(tmpdir(), "hal-boards-"));
    writeFileSync(join(dir, "only.yaml"), validYaml, "utf8");
    const registry = HalRegistry.fromDir(dir);
    expect(registry.listBoards()).toHaveLength(1);
    expect(registry.getBoard("esp32").name).toContain("ESP32");
  });
});
