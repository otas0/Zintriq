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

## Signed Desktop pack (optional)

Repo Actions secrets for a signed tag build (none are set yet — unsigned pack is the default):

- `CSC_LINK` / `CSC_KEY_PASSWORD` (macOS Developer ID .p12)
- `WIN_CSC_LINK` / `WIN_CSC_KEY_PASSWORD` (Authenticode .p12)
- `APPLE_ID` / `APPLE_APP_SPECIFIC_PASSWORD` / `APPLE_TEAM_ID` (notarize)

After secrets exist, tag with `ZINTRIQ_SIGN=1` documented in `desktop/packaging/run-builder.js`, or rely on non-empty `CSC_*` during `Desktop pack`. Daily tags use a **slim** OS matrix; full matrix: tag `v*-release` or `workflow_dispatch` with `full_matrix=true`. Successful tag packs also publish a GitHub Release with installer artifacts.
