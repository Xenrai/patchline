"""An offline, installed-package demo using real diff and scan code."""
import json
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from .scanner import scan_repo
from .spec_diff import diff_specs, summarize


def run_demo():
    data = files("patchline").joinpath("demo_data")
    old = json.loads(data.joinpath("before.json").read_text(encoding="utf-8"))
    new = json.loads(data.joinpath("after.json").read_text(encoding="utf-8"))
    changes = diff_specs(old, new)
    summary = summarize(changes)
    with TemporaryDirectory(prefix="patchline-demo-") as directory:
        for name in ("billing.js", "refunds.js"):
            Path(directory, name).write_text(data.joinpath(name).read_text(encoding="utf-8"),
                                            encoding="utf-8")
        sites = scan_repo(directory, changes)
    print("Patchline demo: a payment API changes; find the callers to review.")
    print(f"{summary['breaking']} breaking changes -> {len(sites)} potential call sites\n")
    for site in sites:
        print(f"  {site.file}:{site.line} [{site.change_kind}] {site.code}")
    print("\nThe scanner suggests review locations; it does not prove a caller is broken.")
    print("No network requests were made and your project files were not changed.")
    print("\nTry your API:")
    print("  patchline diff before.json after.json --out report.json")
    print("  patchline scan --repo . --report report.json")
    print("\nDemo completed. In normal use, findings exit 1; input errors exit 2.")
    return 0
