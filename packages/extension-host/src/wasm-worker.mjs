import { readFileSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import { parentPort, workerData } from "node:worker_threads";

const IMPORT_CAPABILITY = {
  fs_read: "fs.read",
  fs_write: "fs.write",
  net: "net",
  serial: "serial",
  process: "process",
};

function postAudit(capability) {
  parentPort.postMessage({
    audit: {
      timestamp: new Date().toISOString(),
      extensionId: workerData.extensionId,
      capability,
      action: "denied",
    },
  });
}

function readAllowed(rel) {
  if (!rel || rel.includes("\0") || rel.includes("..") || isAbsolute(rel)) {
    throw new Error("path not allowed");
  }
  const root = resolve(workerData.allowRoot);
  const full = resolve(root, rel);
  const diff = relative(root, full);
  if (!diff || diff.startsWith("..") || isAbsolute(diff)) {
    throw new Error("path not allowed");
  }
  return readFileSync(full);
}

const bytes = Buffer.from(workerData.wasmBase64, "base64");
const module = new WebAssembly.Module(bytes);
const maxPages = Math.max(1, Math.floor((workerData.memoryLimitMb * 1024 * 1024) / 65536));
const memory = new WebAssembly.Memory({ initial: 1, maximum: maxPages });
const imports = { env: { memory }, host: {} };

function hostCall(capability, fn) {
  return (...args) => {
    const allowed = workerData.capabilities.includes(capability);
    if (!allowed) {
      postAudit(capability);
      throw new Error(`CAPABILITY_DENIED:${capability}`);
    }
    return fn(...args);
  };
}

for (const entry of WebAssembly.Module.imports(module)) {
  if (entry.kind !== "function") continue;
  const capability = IMPORT_CAPABILITY[entry.name];
  if (!capability) {
    throw new Error(`unknown import ${entry.module}.${entry.name}`);
  }
  const ns = imports[entry.module] ?? {};
  ns[entry.name] = hostCall(capability, (...args) => {
    if (entry.name === "fs_read") {
      const ptr = Number(args[0] ?? 0);
      const len = Number(args[1] ?? 0);
      const rel = new TextDecoder().decode(new Uint8Array(memory.buffer, ptr, len));
      return readAllowed(rel).length;
    }
    return 0;
  });
  imports[entry.module] = ns;
}

try {
  const instance = new WebAssembly.Instance(module, imports);
  const run = instance.exports.run;
  if (typeof run !== "function") {
    throw new Error("wasm export run is missing");
  }
  const output = run(workerData.input);
  parentPort.postMessage({ ok: true, output });
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  const denied = message.match(/CAPABILITY_DENIED:([^\s]+)/);
  if (denied) {
    parentPort.postMessage({
      ok: false,
      error: { code: "CAPABILITY_DENIED", capability: denied[1], message },
    });
  } else if (workerData.input === 2) {
    parentPort.postMessage({
      ok: false,
      error: { code: "EXTENSION_OOM", message: `memory limit ${workerData.memoryLimitMb}MB exceeded` },
    });
  } else {
    parentPort.postMessage({
      ok: false,
      error: { code: "wasm_error", message },
    });
  }
}
