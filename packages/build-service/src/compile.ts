import * as fs from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join, dirname, normalize, sep } from "node:path";
import {
  BoardConfigSchema,
  BuildRequestSchema,
  BuildResultSchema,
  validateOrThrow,
  type BoardConfig,
  type BuildRequest,
  type BuildResult,
  type Diagnostic,
} from "@zintriq/protocol";
import { parseCompilerDiagnostics } from "./diagnostics.js";
import { BUILD_TIMEOUT, COMPILER_NOT_FOUND, BuildServiceError } from "./errors.js";
import { DEFAULT_TIMEOUT_MS, spawnCompiler, type CompilerSpawn } from "./spawn.js";

export type CompileCheckOptions = {
  spawn?: CompilerSpawn;
  timeoutMs?: number;
  removeDir?: (path: string) => Promise<void>;
};

function assertSafeRelative(path: string): string {
  if (!path || isAbsolute(path) || path.includes("\0")) {
    throw new BuildServiceError("invalid_path", `unsafe path: ${path}`);
  }
  const parts = normalize(path).split(/[/\\]/);
  if (parts.includes("..")) {
    throw new BuildServiceError("invalid_path", `path escapes workspace: ${path}`);
  }
  return parts.filter(Boolean).join("/");
}

function failed(diagnostics: Diagnostic[], durationMs: number, rawOutput?: string): BuildResult {
  const result: BuildResult = {
    status: "failed",
    diagnostics,
    durationMs,
    ...(rawOutput ? { rawOutput } : {}),
  };
  return validateOrThrow(BuildResultSchema, result, "build result");
}

export async function compileCheck(
  requestInput: BuildRequest,
  boardInput: BoardConfig,
  options: CompileCheckOptions = {},
): Promise<BuildResult> {
  const request = validateOrThrow(BuildRequestSchema, requestInput, "build request");
  const board = validateOrThrow(BoardConfigSchema, boardInput, "board");
  if (request.boardId !== board.id) {
    throw new BuildServiceError(
      "board_mismatch",
      `request boardId ${request.boardId} does not match board ${board.id}`,
    );
  }
  const entry = assertSafeRelative(request.entryFile);
  const files = request.files.map((file) => ({
    path: assertSafeRelative(file.path),
    content: file.content,
  }));
  if (!files.some((file) => file.path === entry)) {
    throw new BuildServiceError("missing_entry", `entry file not in request: ${entry}`);
  }

  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const spawn = options.spawn ?? spawnCompiler;
  const removeDir = options.removeDir ?? ((path: string) => fs.rm(path, { recursive: true, force: true }));
  const started = Date.now();
  const root = await fs.mkdtemp(join(tmpdir(), "zintriq-build-"));
  try {
    for (const file of files) {
      const dest = join(root, file.path);
      const rootPrefix = root.endsWith(sep) ? root : root + sep;
      if (!dest.startsWith(rootPrefix)) {
        throw new BuildServiceError("invalid_path", `path escapes workspace: ${file.path}`);
      }
      await fs.mkdir(dirname(dest), { recursive: true });
      await fs.writeFile(dest, file.content, "utf8");
    }

    let result;
    try {
      result = await spawn(board.toolchain.compiler, [...board.toolchain.flags, entry], {
        cwd: root,
        timeoutMs,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const code = err && typeof err === "object" && "code" in err ? String(err.code) : "";
      const missing = code === "ENOENT" || code === "EACCES" || /ENOENT|EACCES|not found/i.test(message);
      const diagnosticMessage = missing
        ? `${COMPILER_NOT_FOUND}: compiler "${board.toolchain.compiler}" is missing or not executable. Install g++ or gcc and ensure it is on PATH.`
        : `compiler failed to start: ${message}`;
      return failed(
        [
          {
            file: entry,
            line: 1,
            column: 1,
            severity: "error",
            message: diagnosticMessage,
          },
        ],
        Date.now() - started,
        message,
      );
    }

    const rawStderr = result.stderr.trim();
    const rawOutput = `${result.stderr}${result.stdout}`.trim();
    const durationMs = Date.now() - started;
    if (result.timedOut) {
      return failed(
        [
          {
            file: entry,
            line: 1,
            column: 1,
            severity: "error",
            message: `${BUILD_TIMEOUT}: compile timed out after ${timeoutMs}ms`,
          },
        ],
        durationMs,
        rawOutput,
      );
    }

    const diagnostics = parseCompilerDiagnostics(rawOutput, entry);
    if (result.code === 0) {
      const ok: BuildResult = {
        status: "success",
        diagnostics,
        durationMs,
        ...(rawOutput ? { rawOutput } : {}),
      };
      return validateOrThrow(BuildResultSchema, ok, "build result");
    }

    if (diagnostics.length === 0) {
      const raw = rawStderr || rawOutput || `compiler exited with code ${result.code ?? "null"}`;
      return failed(
        [
          {
            file: entry,
            line: 1,
            column: 1,
            severity: "error",
            message: raw,
          },
        ],
        durationMs,
        rawStderr || rawOutput,
      );
    }
    return failed(diagnostics, durationMs, rawStderr || rawOutput);
  } finally {
    try {
      await removeDir(root);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`build temp cleanup failed for ${root}: ${message}`);
    }
  }
}
