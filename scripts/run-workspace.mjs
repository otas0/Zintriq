import { spawnSync } from "node:child_process";

const task = process.argv[2];
if (!task) {
  console.error("usage: node scripts/run-workspace.mjs <script>");
  process.exit(2);
}

const result = spawnSync(
  "corepack",
  ["pnpm", "-r", "--filter", "./packages/*", "--filter", "./apps/*", "--if-present", "run", task],
  { stdio: "inherit" },
);

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
