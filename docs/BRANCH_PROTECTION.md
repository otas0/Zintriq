# Branch protection / required checks

Desired **main** required status checks (typed MVP only):

- `lint`
- `typecheck`
- `test`
- `build`

Optionally also require the aggregate job `required (lint typecheck test build)` from `.github/workflows/ci.yml`.

Do **not** require: `integration (g++ / non-blocking)`, Desktop pack/smoke, Tauri build, or Playwright e2e.

## Current limitation

On a private repository without GitHub Pro, the Branch protection / Rulesets APIs return HTTP 403. When the plan allows it (Pro or public repo), configure those four checks in Settings → Branches → Branch protection rules for `main`.

## When Pro / public is enabled

1. Settings → Branches → Add rule → Branch name pattern `main`.
2. Enable **Require status checks to pass before merging**.
3. Select only: `lint`, `typecheck`, `test`, `build` (or the aggregate `required (lint typecheck test build)`).
4. Do not select integration, Desktop pack/smoke, Tauri build, or Playwright e2e.
