"""Reproduce the headline numbers: diff two real Stripe OpenAPI specs.

Downloads the pinned spec snapshots from Stripe's public openapi repo
(github.com/stripe/openapi), runs the patchline differ, and writes the full
JSON report next to this script.

Usage:
    python examples/stripe/run_stripe_diff.py

Expected output (v0.3, verified 2026-09-19):
    6385 changes: 4 BREAKING, 1 review, 6380 additive

The report committed at examples/stripe/stripe-diff-report.json was produced
by exactly this script. If Stripe re-tags a release the numbers can shift;
that is the point of pinning tags.
"""
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))  # repo root, so `patchline` imports

from patchline.spec_diff import diff_specs, load_spec, summarize  # noqa: E402

SPECS = {
    "v2250": "https://raw.githubusercontent.com/stripe/openapi/v2250/openapi/spec3.json",
    "v2349": "https://raw.githubusercontent.com/stripe/openapi/v2349/openapi/spec3.json",
}

EXPECTED = {"total": 6385, "breaking": 4, "review": 1, "additive": 6380}


def fetch(tag: str) -> Path:
    dest = HERE / f"spec3_{tag}.json"
    if not dest.exists():
        print(f"downloading {tag} spec (~8MB)...")
        with urllib.request.urlopen(SPECS[tag], timeout=120) as r, open(dest, "wb") as f:
            f.write(r.read())
    return dest


def main() -> int:
    old = load_spec(fetch("v2250"))
    new = load_spec(fetch("v2349"))
    changes = diff_specs(old, new)
    s = summarize(changes)
    print(f"Stripe API: {old['info']['version']} -> {new['info']['version']}")
    print(f"{s['total']} changes: {s['breaking']} BREAKING, {s['review']} review, {s['additive']} additive")

    report = {
        "api": old["info"]["title"],
        "old_version": old["info"]["version"],
        "new_version": new["info"]["version"],
        "specs": SPECS,
        "summary": s,
        "changes": [c.to_dict() for c in changes],
    }
    out = HERE / "stripe-diff-report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"full report -> {out}")

    breaking = [c for c in changes if c.severity in ("BREAKING", "REVIEW")]
    print("\nbreaking changes and manual reviews:")
    for c in breaking:
        print(f"  [{c.severity}] {c.method.upper():5s} {c.path:55s} {c.detail}")

    ok = all(s[k] == v for k, v in EXPECTED.items())
    print(f"\nexpected {EXPECTED} -> {'MATCH' if ok else 'MISMATCH'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
