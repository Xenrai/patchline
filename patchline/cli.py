"""Patchline CLI.

Usage:
  patchline diff OLD_SPEC NEW_SPEC [--out report.json]
  patchline scan --repo PATH --report report.json [--out sites.json]
"""
import argparse
import json
import sys

from .spec_diff import Change, load_spec, diff_specs, summarize
from .scanner import scan_repo


def _cmd_diff(args):
    old = load_spec(args.old_spec)
    new = load_spec(args.new_spec)
    changes = diff_specs(old, new)
    report = {
        "api": old.get("info", {}).get("title", "unknown"),
        "old_version": old.get("info", {}).get("version", "?"),
        "new_version": new.get("info", {}).get("version", "?"),
        "summary": summarize(changes),
        "changes": [c.to_dict() for c in changes],
    }
    s = report["summary"]
    print(f"{report['api']}: {report['old_version']} -> {report['new_version']}")
    print(f"{s['total']} changes: {s['breaking']} BREAKING, {s['additive']} additive")
    print()
    for c in changes:
        if c.severity == "BREAKING":
            print(f"  [BREAKING] {c.kind:24s} {c.method.upper():5s} {c.path:40s} {c.detail}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nFull report written to {args.out}")
    return 1 if s["breaking"] else 0  # exit code doubles as a CI signal


def _cmd_scan(args):
    with open(args.report, "r", encoding="utf-8") as f:
        report = json.load(f)
    changes = [Change(**c) for c in report["changes"]]
    sites = scan_repo(args.repo, changes)
    breaking = [c for c in changes if c.severity == "BREAKING"]
    print(f"{len(breaking)} breaking changes -> {len(sites)} affected call site(s) in {args.repo}")
    print()
    for s_ in sites:
        print(f"  {s_.file}:{s_.line:<5} [{s_.change_kind}] {s_.code[:80]}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([s_.to_dict() for s_ in sites], f, indent=2)
        print(f"\nCall-site report written to {args.out}")
    return 1 if sites else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="patchline",
        description="Diff API specs and find what breaks your code.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diff", help="diff two OpenAPI specs")
    d.add_argument("old_spec")
    d.add_argument("new_spec")
    d.add_argument("--out", help="write full JSON report to this path")
    d.set_defaults(fn=_cmd_diff)

    s = sub.add_parser("scan", help="map a diff report to call sites in a repo")
    s.add_argument("--repo", required=True)
    s.add_argument("--report", required=True)
    s.add_argument("--out", help="write call-site JSON report to this path")
    s.set_defaults(fn=_cmd_scan)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
