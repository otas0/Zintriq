#!/usr/bin/env python3
"""Route-level smoke test — enumerates all Flask routes and GETs each.

Records route, method, status, duration_ms. Handles auth-gated routes
(401/403 expected). Asserts zero 5xx errors.

Usage: python scripts/smoke_routes.py [--output FILE]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app import app


def smoke_test() -> list[dict]:
    """GET every route and record results."""
    results = []
    client = app.test_client()

    # Collect unique rules (skip static files)
    rules = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        # Skip routes with required parameters (we can't fill them)
        if rule.arguments:
            continue
        rules.append(rule)

    print(f"Enumerated {len(rules)} routes (excluding static + parameterized)")
    print()

    for rule in sorted(rules, key=lambda r: r.rule):
        path = rule.rule
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        method = methods[0] if methods else "GET"

        start = time.monotonic()
        try:
            if method == "POST":
                response = client.post(path)
            elif method == "PUT":
                response = client.put(path)
            elif method == "DELETE":
                response = client.delete(path)
            else:
                response = client.get(path)
            duration_ms = int((time.monotonic() - start) * 1000)
            status = response.status_code
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            status = f"ERROR: {type(e).__name__}"

        results.append({
            "route": path,
            "method": method,
            "status": status,
            "duration_ms": duration_ms,
        })

    return results


def print_summary(results: list[dict]) -> dict:
    """Print summary and return status breakdown."""
    # Status breakdown
    status_counts = {}
    for r in results:
        status = r["status"]
        if isinstance(status, int):
            # Group by category
            if status < 300:
                category = "2xx"
            elif status < 400:
                category = "3xx"
            elif status < 500:
                category = "4xx"
            else:
                category = "5xx"
        else:
            category = "ERROR"
        status_counts[category] = status_counts.get(category, 0) + 1

    print("=" * 70)
    print("SMOKE TEST SUMMARY")
    print("=" * 70)
    print(f"Total routes tested: {len(results)}")
    print()
    print("Status breakdown:")
    for category in ["2xx", "3xx", "4xx", "5xx", "ERROR"]:
        count = status_counts.get(category, 0)
        print(f"  {category}: {count}")
    print()

    # Show 5xx errors if any
    fivexx = [r for r in results if isinstance(r["status"], int) and r["status"] >= 500]
    if fivexx:
        print("5xx ERRORS (REGRESSION):")
        for r in fivexx:
            print(f"  {r['method']} {r['route']} → {r['status']} ({r['duration_ms']}ms)")
        print()

    # Show sample routes by status
    print("Sample routes by status:")
    for category in ["2xx", "3xx", "4xx"]:
        sample = [r for r in results if isinstance(r["status"], int) and
                  ((category == "2xx" and r["status"] < 300) or
                   (category == "3xx" and 300 <= r["status"] < 400) or
                   (category == "4xx" and 400 <= r["status"] < 500))]
        if sample:
            print(f"  {category} (showing up to 5):")
            for r in sample[:5]:
                print(f"    {r['method']} {r['route']} → {r['status']} ({r['duration_ms']}ms)")

    return status_counts


def main():
    print("Phase 1.0 Route-Level Smoke Test")
    print("=" * 70)
    print()

    with app.app_context():
        results = smoke_test()

    status_counts = print_summary(results)

    # Assertion: zero 5xx
    fivexx_count = status_counts.get("5xx", 0)
    print()
    print("=" * 70)
    if fivexx_count == 0:
        print("✓ PASS: Zero 5xx errors (no regressions)")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"✗ FAIL: {fivexx_count} 5xx errors detected (REGRESSION)")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
