"""Tests for the call-site scanner: pattern heuristics on JS/TS code.

Run: python -m unittest discover tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patchline.scanner import scan_repo  # noqa: E402
from patchline.spec_diff import Change  # noqa: E402


def write(repo: Path, name: str, content: str):
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def change(kind, path="/v1/charges/{id}", pointer="paths./v1/charges/{id}.get",
           old=None):
    return Change(kind=kind, severity="BREAKING", path=path, method="get",
                  detail="test", pointer=pointer, old=old)


class TestScanner(unittest.TestCase):
    def test_endpoint_literal_with_param(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            write(repo, "billing.js",
                  'const url = `/v1/charges/${id}`;\nconst other = 1;\n')
            sites = scan_repo(str(repo), [change("endpoint_removed")])
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0].file, "billing.js")
            self.assertEqual(sites[0].line, 1)

    def test_response_field_access(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            write(repo, "billing.js",
                  "return charge.billing_details.address.split(',');\n")
            c = change("response_field_removed", path="/v1/charges",
                       pointer="paths./v1/charges.get.responses.200.billing_details.address")
            sites = scan_repo(str(repo), [c])
            self.assertTrue(sites)

    def test_enum_string_match(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            write(repo, "state.js", "if (charge.status === 'pending') retry();\n")
            c = change("enum_value_removed", old="pending")
            sites = scan_repo(str(repo), [c])
            self.assertEqual(len(sites), 1)

    def test_additive_changes_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            write(repo, "billing.js", 'const url = "/v1/charges/ch_123";\n')
            additive = Change(kind="endpoint_added", severity="ADDITIVE",
                              path="/v1/charges", method="post",
                              detail="test", pointer="p")
            sites = scan_repo(str(repo), [additive])
            self.assertEqual(sites, [])

    def test_dedup_same_line_same_change(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            write(repo, "a.js", 'x("/v1/charges/"); y("/v1/charges/");\n')
            sites = scan_repo(str(repo), [change("endpoint_removed")])
            keys = [(s.file, s.line, s.change_pointer) for s in sites]
            self.assertEqual(len(keys), len(set(keys)))

    def test_non_js_files_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            write(repo, "notes.md", "/v1/charges/{id}\n")
            sites = scan_repo(str(repo), [change("endpoint_removed")])
            self.assertEqual(sites, [])


if __name__ == "__main__":
    unittest.main()
