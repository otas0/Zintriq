import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
import { describe, expect, it } from "vitest";
import { parseBoardConfig } from "./validate-board.js";

const boardsDir = fileURLToPath(new URL("../../../fixtures/boards", import.meta.url));

describe("HAL board JSON Schema alignment", () => {
  it("ships board.schema.json with required mcuFamily enum", () => {
    const schema = JSON.parse(readFileSync(join(boardsDir, "board.schema.json"), "utf8")) as {
      properties: { mcuFamily: { enum: string[] } };
      required: string[];
    };
    expect(schema.required).toEqual(expect.arrayContaining(["id", "name", "mcuFamily", "toolchain", "pins"]));
    expect(schema.properties.mcuFamily.enum).toEqual(["esp32", "stm32", "rp2040"]);
  });

  it("validates every shipped YAML board against BoardConfigSchema", () => {
    const files = readdirSync(boardsDir).filter((name) => name.endsWith(".yaml"));
    expect(files.length).toBeGreaterThan(0);
    for (const name of files) {
      const raw = parseYaml(readFileSync(join(boardsDir, name), "utf8"));
      expect(() => parseBoardConfig(raw), name).not.toThrow();
    }
  });

  it("rejects schema negatives: unknown mcuFamily, empty id, extra top-level field", () => {
    expect(() =>
      parseBoardConfig({
        id: "bad-mcu",
        name: "Bad",
        mcuFamily: "nrf52",
        toolchain: { compiler: "g++", flags: [] },
        pins: { LED: "P0" },
      }),
    ).toThrow();

    expect(() =>
      parseBoardConfig({
        id: "",
        name: "Empty id",
        mcuFamily: "esp32",
        toolchain: { compiler: "g++", flags: [] },
        pins: { LED: "GPIO2" },
      }),
    ).toThrow();

    expect(() =>
      parseBoardConfig({
        id: "extra",
        name: "Extra",
        mcuFamily: "stm32",
        toolchain: { compiler: "g++", flags: [] },
        pins: { LED: "PA5" },
        flashKb: 128,
      }),
    ).toThrow();
  });
});
