import {
  BoardConfigSchema,
  ValidationError,
  validateOrThrow,
  type BoardConfig,
} from "@zintriq/protocol";
import { HalRegistryError } from "./errors.js";

export function findPinConflicts(pins: Record<string, string>): string[] {
  const byPhysical = new Map<string, string[]>();
  for (const [logical, physical] of Object.entries(pins)) {
    const list = byPhysical.get(physical) ?? [];
    list.push(logical);
    byPhysical.set(physical, list);
  }
  const conflicts: string[] = [];
  for (const [physical, logicals] of byPhysical) {
    if (logicals.length > 1) {
      conflicts.push(`${physical} claimed by ${logicals.sort().join(", ")}`);
    }
  }
  return conflicts.sort();
}

export function parseBoardConfig(raw: unknown): BoardConfig {
  let board: BoardConfig;
  try {
    board = validateOrThrow(BoardConfigSchema, raw, "board config");
  } catch (err) {
    if (err instanceof ValidationError) {
      throw new HalRegistryError("invalid_board", err.message, err.issues);
    }
    throw err;
  }

  if (!board.toolchain.compiler.trim()) {
    throw new HalRegistryError("missing_toolchain", "toolchain.compiler is required");
  }

  const conflicts = findPinConflicts(board.pins);
  if (conflicts.length > 0) {
    throw new HalRegistryError("pin_conflict", "duplicate physical pin assignments", {
      conflicts,
    });
  }

  return board;
}
