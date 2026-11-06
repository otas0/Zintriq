import { spawn } from "node:child_process";

export type SpawnResult = {
  code: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
};

export type CompilerSpawn = (
  command: string,
  args: string[],
  options: { cwd: string; timeoutMs: number },
) => Promise<SpawnResult>;

export const DEFAULT_TIMEOUT_MS = 30_000;

export const spawnCompiler: CompilerSpawn = (command, args, options) =>
  new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: options.cwd, shell: false });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, options.timeoutMs);

    child.stdout?.setEncoding("utf8");
    child.stderr?.setEncoding("utf8");
    child.stdout?.on("data", (chunk: string) => {
      stdout += chunk;
    });
    child.stderr?.on("data", (chunk: string) => {
      stderr += chunk;
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code, stdout, stderr, timedOut });
    });
  });
