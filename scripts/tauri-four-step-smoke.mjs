#!/usr/bin/env node
/**
 * Scripted stand-in for the Tauri GUI four-step hand-test:
 *   open folder → allow → save → stub compile_commands → connect clangd
 *
 * Automates what does not need the window: temp workspace + stub JSON +
 * real /usr/bin/clangd diagnostics via @zintriq/lsp-client.
 * Open/allow/save still need interactive `pnpm --filter @zintriq/desktop tauri dev`
 * (or a future WebDriver harness); this script prints that checklist.
 */
import { mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { createLspClient } from "../packages/lsp-client/dist/index.js";

const which = spawnSync("which", ["clangd"], { encoding: "utf8" });
if (which.status !== 0) {
  console.error("clangd not on PATH — install LLVM/clangd before four-step smoke");
  process.exit(1);
}
const clangdPath = which.stdout.trim();
console.log("clangd:", clangdPath);

const root = join(tmpdir(), `zintriq-four-step-${Date.now()}`);
mkdirSync(root, { recursive: true });
const mainCpp = join(root, "main.cpp");
writeFileSync(mainCpp, "int main(){ return }\n");

// Step: stub compile_commands (same shape as App.tsx generate stub)
const stub = [
  {
    directory: root,
    command: "clang++ -std=c++17 -c main.cpp -o main.o",
    file: "main.cpp",
  },
];
const ccPath = join(root, "compile_commands.json");
writeFileSync(ccPath, `${JSON.stringify(stub, null, 2)}\n`);
console.log("stub compile_commands →", ccPath);

if (!existsSync(join(process.cwd(), "packages/lsp-client/dist/index.js"))) {
  console.log("building @zintriq/lsp-client…");
  const build = spawnSync("corepack", ["pnpm", "--filter", "@zintriq/lsp-client", "run", "build"], {
    cwd: process.cwd(),
    stdio: "inherit",
  });
  if (build.status !== 0) process.exit(build.status ?? 1);
}

const rootUri = `file://${root}`;
const fileUri = `file://${mainCpp}`;
const client = createLspClient({
  rootUri,
  languageId: "cpp",
  server: { command: "clangd", args: [`--compile-commands-dir=${root}`] },
});

const diags = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("timed out waiting for clangd diagnostics")), 20_000);
  const off = client.onDiagnostics((event) => {
    if (event.uri.includes("main.cpp") && event.diagnostics.length > 0) {
      clearTimeout(timer);
      off();
      resolve(event.diagnostics);
    }
  });
  client
    .initialize()
    .then(() => client.didOpen(fileUri, "int main(){ return }\n"))
    .catch((err) => {
      clearTimeout(timer);
      reject(err);
    });
});

client.dispose();
rmSync(root, { recursive: true, force: true });

console.log(
  JSON.stringify(
    {
      ok: true,
      automated: ["stub compile_commands", "connect real clangd", "publishDiagnostics"],
      interactiveStillNeeded: ["open folder (Tauri dialog)", "allow fs permission", "save file"],
      clangdPath,
      diagnosticCount: diags.length,
      sample: diags.slice(0, 3).map((d) => d.message),
    },
    null,
    2,
  ),
);
console.log(
  "\nInteractive remainder: cd apps/desktop && corepack pnpm exec tauri dev\n  → 打开文件夹 → 允许 → 保存 → 一键 stub（若需要）→ 连接 clangd",
);
