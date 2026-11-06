import type { BoardConfig } from "@zintriq/protocol";
import { HalRegistryError } from "./errors.js";
import { loadBoardsFromDir, resolveBoardsDir } from "./load.js";

export class HalRegistry {
  private readonly boards: Map<string, BoardConfig>;

  constructor(boards: Map<string, BoardConfig>) {
    this.boards = boards;
  }

  static fromDir(dir?: string): HalRegistry {
    return new HalRegistry(loadBoardsFromDir(resolveBoardsDir(dir)));
  }

  listBoards(): BoardConfig[] {
    return [...this.boards.values()].sort((a, b) => a.id.localeCompare(b.id));
  }

  getBoard(id: string): BoardConfig {
    const board = this.boards.get(id);
    if (!board) {
      throw new HalRegistryError("board_not_found", `unknown board id: ${id}`);
    }
    return board;
  }
}

let defaultRegistry: HalRegistry | undefined;

export function getDefaultRegistry(): HalRegistry {
  if (!defaultRegistry) {
    defaultRegistry = HalRegistry.fromDir();
  }
  return defaultRegistry;
}

export function listBoards(): BoardConfig[] {
  return getDefaultRegistry().listBoards();
}

export function getBoard(id: string): BoardConfig {
  return getDefaultRegistry().getBoard(id);
}

/** Test helper — clears the cached default registry. */
export function resetDefaultRegistry(): void {
  defaultRegistry = undefined;
}
