import { spawnSync } from "node:child_process";

export type DetectedServer = {
  id: "clangd" | "pylsp";
  command: string;
  available: boolean;
  detail: string;
};

function probe(command: string, args: string[]): { available: boolean; detail: string } {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.error) {
    const code = "code" in result.error ? String(result.error.code) : "";
    return {
      available: false,
      detail: code === "ENOENT" ? `${command} not found on PATH` : result.error.message,
    };
  }
  if (result.status !== 0) {
    return { available: false, detail: (result.stderr || result.stdout || `exit ${result.status}`).trim() };
  }
  const line = (result.stdout || result.stderr).split(/\r?\n/).find((item) => item.trim()) ?? "ok";
  return { available: true, detail: line.trim() };
}

/** Probe local language servers. CI and the desktop MVP keep using the mock transport. */
export function detectLanguageServers(): DetectedServer[] {
  const clangd = probe("clangd", ["--version"]);
  const pylsp = probe("pylsp", ["--version"]);
  return [
    { id: "clangd", command: "clangd", available: clangd.available, detail: clangd.detail },
    { id: "pylsp", command: "pylsp", available: pylsp.available, detail: pylsp.detail },
  ];
}
