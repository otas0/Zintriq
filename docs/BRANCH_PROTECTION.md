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
