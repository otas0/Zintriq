#!/usr/bin/env node
/**
 * Hand smoke: spawn clangd over stdio via @zintriq/lsp-client, open broken C++,
 * wait for publishDiagnostics. Explicit connect only — no edit loop.
 */
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createLspClient } from "../packages/lsp-client/dist/index.js";

const root = join(tmpdir(), `zintriq-clangd-${Date.now()}`);
mkdirSync(root, { recursive: true });
const filePath = join(root, "main.cpp");
writeFileSync(filePath, "int main(){ return }\n");
const rootUri = `file://${root}`;
const fileUri = `file://${filePath}`;

const client = createLspClient({
  rootUri,
  languageId: "cpp",
  server: { command: "clangd", args: [] },
});

const diags = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("timed out waiting for clangd diagnostics")), 15_000);
  const off = client.onDiagnostics((event) => {
    if (event.uri.includes("main.cpp") && event.diagnostics.length > 0) {
      clearTimeout(timer);
      off();
      resolve(event.diagnostics);
    }
  });
  client
    .initialize()
    .then(() => {
      client.didOpen(fileUri, "int main(){ return }\n");
    })
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
      count: diags.length,
      sample: diags.slice(0, 3).map((d) => d.message),
    },
    null,
    2,
  ),
);
