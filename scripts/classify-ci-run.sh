#!/usr/bin/env bash
# Classify a GitHub Actions run: billing/empty-steps vs real step failure.
# Usage: scripts/classify-ci-run.sh [run_id|run_url]
# Exit: 0 ok/skip-only, 1 real failure, 10 billing/empty-steps, 2 usage, 3 unknown
set -euo pipefail
REPO="${GITHUB_REPOSITORY:-otas0/Zintriq}"
RAW="${1:-}"
if [ -z "$RAW" ]; then
  RAW="$(gh run list -R "$REPO" --limit 1 --json databaseId -q '.[0].databaseId')"
fi
RUN_ID="$(printf '%s' "$RAW" | grep -Eo '[0-9]{6,}' | head -1 || true)"
if [ -z "$RUN_ID" ]; then
  echo "usage: $0 <run_id|url>" >&2
  exit 2
fi

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
gh api "repos/$REPO/actions/runs/$RUN_ID/jobs" --paginate >"$TMP"

python3 - "$RUN_ID" "$TMP" <<'PY'
import json, sys
run_id, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
jobs = data.get("jobs") or []
print(f"run={run_id} jobs={len(jobs)}")
billingish, real, skipped = [], [], []
for j in jobs:
    name = j.get("name") or "?"
    conclusion = j.get("conclusion") or j.get("status") or "?"
    steps = j.get("steps") or []
    if conclusion == "skipped":
        skipped.append(name)
        continue
    if conclusion in ("failure", "cancelled", "timed_out") and len(steps) == 0:
        billingish.append(f"{name} ({conclusion}, 0 steps)")
    elif conclusion == "failure":
        failed_steps = [s.get("name", "?") for s in steps if s.get("conclusion") == "failure"]
        real.append(f"{name}: {', '.join(failed_steps) or 'unknown step'}")
    else:
        print(f"  ok  {name}: {conclusion} steps={len(steps)}")

print()
if billingish and not real:
    print("VERDICT: BILLING_OR_QUOTA (empty-step failures — not a test regression)")
    print("Fix GitHub Billing & plans / Actions spending limit, then re-run.")
    print("Do not cut a new -release tag until Actions accepts jobs with real steps.")
    for line in billingish:
        print(f"  - {line}")
    sys.exit(10)
if real:
    print("VERDICT: REAL_FAILURE (steps ran and failed)")
    for line in real:
        print(f"  - {line}")
    if billingish:
        print("also empty-step jobs (may be cascade):")
        for line in billingish:
            print(f"  - {line}")
    sys.exit(1)
print("VERDICT: SKIPPED_ONLY / SUCCESS_PATH")
sys.exit(0)
PY
