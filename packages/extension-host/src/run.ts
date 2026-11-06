import { readFile } from "node:fs/promises";
import { isAbsolute, join } from "node:path";
import { Worker } from "node:worker_threads";
import { fileURLToPath } from "node:url";
import {
  ExtensionManifestSchema,
  ExtensionRunResultSchema,
  validateOrThrow,
  ValidationError,
  type ExtensionManifest,
  type ExtensionRunResult,
} from "@zintriq/protocol";
import { recordAudit, type AuditEntry } from "./audit.js";
import { CapabilityDeniedError, EXTENSION_OOM, EXTENSION_TIMEOUT } from "./errors.js";

const FIXTURES_DIR = fileURLToPath(new URL("../../../fixtures/extensions", import.meta.url));
const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_MEMORY_MB = 64;

type WorkerMessage =
  | { audit: AuditEntry }
  | { ok: true; output: unknown }
  | { ok: false; error: { code: string; capability?: string; message: string } };

function assertManifest(input: unknown): ExtensionManifest {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    throw new ValidationError("extension manifest failed validation", [
      { path: "", message: "expected object" },
    ]);
  }
  if (!("capabilities" in input)) {
    throw new ValidationError("extension manifest failed validation: capabilities required", [
      { path: "capabilities", message: "required" },
    ]);
  }
  return validateOrThrow(ExtensionManifestSchema, input, "extension manifest");
}

function modeOf(input: unknown): number {
  if (typeof input === "number") return input;
  if (input && typeof input === "object" && "mode" in input && typeof input.mode === "number") {
    return input.mode;
  }
  return 0;
}

function resolveWasm(entryWasm: string): string {
  return isAbsolute(entryWasm) ? entryWasm : join(FIXTURES_DIR, entryWasm);
}

export async function runExtension(
  manifestInput: unknown,
  input: unknown = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
  memoryLimitMb = DEFAULT_MEMORY_MB,
): Promise<ExtensionRunResult> {
  const started = Date.now();
  const finish = (body: Omit<ExtensionRunResult, "durationMs">): ExtensionRunResult =>
    validateOrThrow(
      ExtensionRunResultSchema,
      { ...body, durationMs: Date.now() - started },
      "extension result",
    );

  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0) {
    throw new Error("timeoutMs must be a positive integer");
  }
  if (!Number.isInteger(memoryLimitMb) || memoryLimitMb <= 0) {
    throw new Error("memoryLimitMb must be a positive integer");
  }
  const manifest = assertManifest(manifestInput);
  const wasm = await readFile(resolveWasm(manifest.entryWasm));
  const worker = new Worker(new URL("./wasm-worker.mjs", import.meta.url), {
    workerData: {
      wasmBase64: wasm.toString("base64"),
      capabilities: manifest.capabilities,
      input: modeOf(input),
      extensionId: manifest.id,
      memoryLimitMb,
      allowRoot: FIXTURES_DIR,
    },
  });

  return new Promise((resolve, reject) => {
    let settled = false;
    const done = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      void worker.terminate();
      fn();
    };
    const timer = setTimeout(() => {
      done(() => {
        resolve(
          finish({
            ok: false,
            error: {
              code: EXTENSION_TIMEOUT,
              message: `extension timed out after ${timeoutMs}ms`,
            },
          }),
        );
      });
    }, timeoutMs);

    worker.on("message", (message: WorkerMessage) => {
      if ("audit" in message) {
        recordAudit(message.audit);
        return;
      }
      done(() => {
        if (message.ok) {
          resolve(finish({ ok: true, output: message.output }));
          return;
        }
        if (message.error.code === "CAPABILITY_DENIED" && message.error.capability) {
          reject(new CapabilityDeniedError(manifest.id, message.error.capability));
          return;
        }
        if (message.error.code === EXTENSION_OOM) {
          resolve(
            finish({
              ok: false,
              error: { code: EXTENSION_OOM, message: message.error.message },
            }),
          );
          return;
        }
        reject(new Error(message.error.message));
      });
    });
    worker.on("error", (err) => {
      done(() => reject(err));
    });
  });
}
