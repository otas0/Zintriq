#!/usr/bin/env python3
"""Verify every payment plugin slug has checkout creator + verifier adapters."""

from __future__ import annotations

import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS, FAIL = [], []

# Handled directly in checkout_platform.py, not via payment_checkout_adapters.
_SPECIAL_CHECKOUT = frozenset({"stripe", "paypal"})


def ok(name, detail=""):
    PASS.append((name, detail))


def fail(name, detail):
    FAIL.append((name, detail))


def _fn_label(fn) -> str:
    if fn is None:
        return "missing"
    name = getattr(fn, "__name__", type(fn).__name__)
    mod = getattr(inspect.getmodule(fn), "__name__", "")
    return f"{mod}.{name}" if mod else name


def run() -> int:
    from integration_catalog import payment_plugin_slugs
    from payment_checkout_adapters import (
        _CREATORS,
        _VERIFIERS,
        create_hosted_checkout,
        verify_hosted_payment,
    )

    slugs = list(payment_plugin_slugs())
    hosted_slugs = [s for s in slugs if s not in _SPECIAL_CHECKOUT]

    ok("Catalog.payment_plugins", f"count={len(slugs)} hosted={len(hosted_slugs)}")
    ok("Registry.creators", f"count={len(_CREATORS)}")
    ok("Registry.verifiers", f"count={len(_VERIFIERS)}")

    for slug in sorted(hosted_slugs):
        creator = _CREATORS.get(slug)
        verifier = _VERIFIERS.get(slug)
        if not creator:
            fail(f"Adapter.{slug}.creator", "missing from _CREATORS")
            continue
        if not verifier:
            fail(f"Adapter.{slug}.verifier", f"creator={_fn_label(creator)}")
            continue
        if not callable(creator):
            fail(f"Adapter.{slug}.creator", "not callable")
            continue
        if not callable(verifier):
            fail(f"Adapter.{slug}.verifier", "not callable")
            continue
        ok(f"Adapter.{slug}", f"creator={_fn_label(creator)} verifier={_fn_label(verifier)}")

    for slug in sorted(_SPECIAL_CHECKOUT):
        if slug in slugs:
            ok(f"Special.{slug}", "checkout handled in checkout_platform.py")
        else:
            fail(f"Special.{slug}", "expected in payment_plugin_slugs()")

    # Smoke: public helpers are wired (no provider HTTP calls).
    probe_fields = {"api_key": "verify_probe", "livemode": False}
    fallback = create_hosted_checkout(
        "__missing_probe__",
        probe_fields,
        amount=1,
        currency="USD",
        description="probe",
        reference="probe-ref",
        return_url="https://example.test/return",
        cancel_url="https://example.test/cancel",
        brand_name="Probe",
        pay_url="https://example.test/pay",
    )
    if fallback.get("checkout_url") == "https://example.test/pay":
        ok("Resolve.fallback_pay_url", "create_hosted_checkout uses pay_url when adapter missing")
    else:
        fail("Resolve.fallback_pay_url", str(fallback))

    for slug in hosted_slugs:
        if slug not in _CREATORS:
            fail(f"Resolve.{slug}", "create_hosted_checkout has no adapter")
            continue
        ok(f"Resolve.{slug}", "create_hosted_checkout wired")

    # Only probe a pure query-based verifier (no outbound HTTP).
    if verify_hosted_payment("square", probe_fields, session_id="probe", query={"status": "paid"}):
        ok("Verify.hosted_ok_sample", "verify_hosted_payment accepts paid callback")
    else:
        fail("Verify.hosted_ok_sample", "expected square/_hosted_ok to accept status=paid")

    missing_creators = [s for s in hosted_slugs if s not in _CREATORS]
    missing_verifiers = [s for s in hosted_slugs if s not in _VERIFIERS]
    if missing_creators:
        fail("Summary.missing_creators", ", ".join(missing_creators))
    else:
        ok("Summary.missing_creators", "none")
    if missing_verifiers:
        fail("Summary.missing_verifiers", ", ".join(missing_verifiers))
    else:
        ok("Summary.missing_verifiers", "none")

    print(f"\n=== Checkout adapters verify: {len(PASS)} passed, {len(FAIL)} failed ===")
    for name, detail in PASS:
        print(f"  OK  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f" FAIL {name}" + (f" — {detail}" if detail else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
