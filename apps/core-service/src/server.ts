import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import cors from "@fastify/cors";
import { compileCheck } from "@zintriq/build-service";
import {
  CapabilityDeniedError,
  EXTENSION_OOM,
  EXTENSION_TIMEOUT,
  getAuditLog,
  runExtension,
} from "@zintriq/extension-host";
import { getBoard, HalRegistryError, listBoards } from "@zintriq/hal-registry";
import {
  BuildRequestSchema,
  ExtensionManifestSchema,
  ExtensionRunRequestSchema,
  validateOrThrow,
  type BoardConfig,
  type BuildRequest,
  type BuildResult,
  type ExtensionManifest,
  type ExtensionRunResult,
} from "@zintriq/protocol";
import Fastify, { type FastifyInstance } from "fastify";
import type { ZodError } from "zod";

const pkg = JSON.parse(
  readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8"),
) as { version: string };

const ALLOWED_ORIGINS = ["http://localhost:5173", "tauri://localhost"];
const EXTENSIONS_DIR = process.env.ZINTRIQ_EXTENSIONS_DIR
  ? process.env.ZINTRIQ_EXTENSIONS_DIR
  : fileURLToPath(new URL("../../../fixtures/extensions", import.meta.url));

export class ApiError extends Error {
  readonly statusCode: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(statusCode: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.code = code;
    if (details !== undefined) {
      this.details = details;
    }
  }
}

export type CompileFn = (request: BuildRequest, board: BoardConfig) => Promise<BuildResult>;

export type RunExtensionFn = (
  manifest: ExtensionManifest,
  input: unknown,
  timeoutMs: number,
  memoryLimitMb: number,
) => Promise<ExtensionRunResult>;

export type BuildAppOptions = {
  compile?: CompileFn;
  runExtension?: RunExtensionFn;
};

function loadExtensions(): ExtensionManifest[] {
  const manifests: ExtensionManifest[] = [];
  for (const name of readdirSync(EXTENSIONS_DIR)) {
    if (!name.endsWith(".json")) continue;
    const raw = JSON.parse(readFileSync(join(EXTENSIONS_DIR, name), "utf8")) as unknown;
    manifests.push(validateOrThrow(ExtensionManifestSchema, raw, name));
  }
  return manifests.sort((a, b) => a.id.localeCompare(b.id));
}

function fieldPaths(error: ZodError): { path: string; message: string }[] {
  return error.issues.map((issue) => ({
    path: issue.path.length > 0 ? issue.path.map(String).join(".") : "",
    message: issue.message,
  }));
}

function loadRegistry(): ReturnType<typeof listBoards> {
  try {
    const boards = listBoards();
    if (boards.length === 0) {
      throw new Error("no boards found");
    }
    return boards;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`hal-registry failed to load: ${message}`);
  }
}

export async function buildApp(options: BuildAppOptions = {}): Promise<FastifyInstance> {
  loadRegistry();
  const startedAt = Date.now();
  const compile = options.compile ?? compileCheck;
  const runGuest = options.runExtension ?? runExtension;
  const app = Fastify({ logger: { level: process.env.LOG_LEVEL ?? "info" } });

  await app.register(cors, {
    origin: ALLOWED_ORIGINS,
    methods: ["GET", "POST"],
    allowedHeaders: ["content-type"],
  });

  app.setErrorHandler((err, _request, reply) => {
    if (err instanceof ApiError) {
      reply.status(err.statusCode).send({
        code: err.code,
        message: err.message,
        ...(err.details !== undefined ? { details: err.details } : {}),
      });
      return;
    }
    if (err instanceof HalRegistryError && err.code === "board_not_found") {
      reply.status(404).send({ code: "BOARD_NOT_FOUND", message: err.message });
      return;
    }
    const statusCode =
      err !== null && typeof err === "object" && "statusCode" in err && typeof err.statusCode === "number"
        ? err.statusCode
        : 500;
    const message = err instanceof Error ? err.message : "request failed";
    if (statusCode >= 400 && statusCode < 500) {
      reply.status(statusCode).send({
        code: statusCode === 400 ? "VALIDATION_ERROR" : "REQUEST_ERROR",
        message,
        ...(statusCode === 400 ? { details: [] } : {}),
      });
      return;
    }
    app.log.error({ err: message }, "unhandled error");
    reply.status(500).send({ code: "INTERNAL_ERROR", message: "internal error" });
  });

  app.get("/health", async () => ({
    status: "ok" as const,
    version: pkg.version,
    uptimeMs: Date.now() - startedAt,
  }));

  app.get("/boards", async () => listBoards());

  app.post("/build", async (request) => {
    const parsed = BuildRequestSchema.safeParse(request.body);
    if (!parsed.success) {
      throw new ApiError(400, "VALIDATION_ERROR", "request failed validation", fieldPaths(parsed.error));
    }
    let board: BoardConfig;
    try {
      board = getBoard(parsed.data.boardId);
    } catch (err) {
      if (err instanceof HalRegistryError && err.code === "board_not_found") {
        throw new ApiError(404, "BOARD_NOT_FOUND", err.message);
      }
      throw err;
    }
    return compile(parsed.data, board);
  });

  app.get("/extensions", async () => ({
    extensions: loadExtensions(),
    extensionsDir: EXTENSIONS_DIR,
  }));

  app.get("/audit", async (request) => {
    const query = request.query as { limit?: string; extensionId?: string };
    const parsed = Number(query.limit ?? 50);
    const limit = Number.isFinite(parsed) ? Math.min(Math.max(Math.trunc(parsed), 1), 500) : 50;
    const extensionId = typeof query.extensionId === "string" ? query.extensionId.trim() : "";
    const all = getAuditLog().filter((entry) => (extensionId ? entry.extensionId === extensionId : true));
    return {
      entries: all.slice(-limit),
      total: all.length,
      extensionsDir: EXTENSIONS_DIR,
      ...(extensionId ? { extensionId } : {}),
    };
  });

  app.post("/extensions/:id/run", async (request) => {
    const params = request.params as { id: string };
    const manifest = loadExtensions().find((item) => item.id === params.id);
    if (!manifest) {
      throw new ApiError(404, "EXTENSION_NOT_FOUND", `unknown extension: ${params.id}`);
    }
    const parsed = ExtensionRunRequestSchema.safeParse(request.body ?? {});
    if (!parsed.success) {
      throw new ApiError(400, "VALIDATION_ERROR", "request failed validation", fieldPaths(parsed.error));
    }
    try {
      const result = await runGuest(manifest, parsed.data.input ?? {}, parsed.data.timeoutMs, parsed.data.memoryLimitMb);
      if (result.ok === false && result.error?.code === EXTENSION_TIMEOUT) {
        throw new ApiError(504, EXTENSION_TIMEOUT, result.error.message);
      }
      if (result.ok === false && result.error?.code === EXTENSION_OOM) {
        throw new ApiError(500, EXTENSION_OOM, result.error.message);
      }
      return result;
    } catch (err) {
      if (err instanceof CapabilityDeniedError) {
        throw new ApiError(403, "CAPABILITY_DENIED", err.message, { capability: err.capability });
      }
      throw err;
    }
  });

  return app;
}
