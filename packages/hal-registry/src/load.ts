import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { BoardConfig } from "@zintriq/protocol";
import { parse as parseYaml } from "yaml";
import { HalRegistryError } from "./errors.js";
import { parseBoardConfig } from "./validate-board.js";

const DEFAULT_BOARDS_DIR = fileURLToPath(new URL("../../../fixtures/boards", import.meta.url));

export function resolveBoardsDir(override?: string): string {
  return override ?? process.env.ZINTRIQ_BOARDS_DIR ?? DEFAULT_BOARDS_DIR;
}

export function loadBoardFromYaml(text: string, source = "inline"): BoardConfig {
  let raw: unknown;
  try {
    raw = parseYaml(text);
  } catch (err) {
    throw new HalRegistryError("invalid_yaml", `failed to parse ${source}`, {
      cause: err instanceof Error ? err.message : String(err),
    });
  }
  return parseBoardConfig(raw);
}

export function loadBoardsFromDir(dir: string): Map<string, BoardConfig> {
  const boards = new Map<string, BoardConfig>();
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch (err) {
    throw new HalRegistryError("boards_dir_missing", `cannot read boards dir: ${dir}`, {
      cause: err instanceof Error ? err.message : String(err),
    });
  }

  for (const name of entries) {
    if (!name.endsWith(".yaml") && !name.endsWith(".yml")) continue;
    const path = join(dir, name);
    const text = readFileSync(path, "utf8");
    const board = loadBoardFromYaml(text, path);
    if (boards.has(board.id)) {
      throw new HalRegistryError("duplicate_board_id", `duplicate board id: ${board.id}`, {
        path,
      });
    }
    boards.set(board.id, board);
  }
  return boards;
}
