"""Tests for the spec differ: one test per change class plus $ref handling.

Run: python -m unittest discover tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patchline.spec_diff import diff_specs, summarize  # noqa: E402


def make_spec(endpoints):
    """Build a minimal OpenAPI-ish spec. Each endpoint: (path, method, op)."""
    paths = {}
    for path, method, op in endpoints:
        paths.setdefault(path, {})[method] = op
    return {"info": {"title": "T", "version": "1"}, "paths": paths}


def op(resp_props=None, req_required=None, resp_enums=None):
    """Build an operation with a simplified inline schema shape."""
    op = {}
    if resp_props is not None or resp_enums is not None:
        props = dict(resp_props or {})
        for name, vals in (resp_enums or {}).items():
            props[name] = {"type": "string", "enum": vals}
        op["responses"] = {"200": {"schema": {"type": "object", "properties": props}}}
    if req_required is not None:
        op["requestBody"] = {
            "required": req_required,
            "properties": {n: {"type": "string"} for n in req_required},
        }
    return op


class TestEndpointChanges(unittest.TestCase):
    def test_endpoint_removed_is_breaking(self):
        old = make_spec([("/a", "get", op(resp_props={"x": {"type": "string"}}))])
        new = make_spec([])
        changes = diff_specs(old, new)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "endpoint_removed")
        self.assertEqual(changes[0].severity, "BREAKING")

    def test_endpoint_added_is_additive(self):
        old = make_spec([])
        new = make_spec([("/a", "get", op())])
        changes = diff_specs(old, new)
        self.assertEqual(changes[0].kind, "endpoint_added")
        self.assertEqual(changes[0].severity, "ADDITIVE")


class TestResponseChanges(unittest.TestCase):
    def _diff(self, old_props, new_props):
        old = make_spec([("/a", "get", op(resp_props=old_props))])
        new = make_spec([("/a", "get", op(resp_props=new_props))])
        return diff_specs(old, new)

    def test_response_field_removed_is_breaking(self):
        changes = self._diff({"iin": {"type": "string"}}, {})
        self.assertEqual(changes[0].kind, "response_field_removed")
        self.assertEqual(changes[0].severity, "BREAKING")

    def test_response_type_changed_is_breaking(self):
        changes = self._diff(
            {"address": {"type": "string"}},
            {"address": {"type": "object"}},
        )
        self.assertEqual(changes[0].kind, "response_type_changed")
        self.assertEqual(changes[0].severity, "BREAKING")

    def test_response_field_added_is_additive(self):
        changes = self._diff({}, {"new_field": {"type": "string"}})
        self.assertEqual(changes[0].kind, "response_field_added")
        self.assertEqual(changes[0].severity, "ADDITIVE")

    def test_nested_field_paths(self):
        changes = self._diff(
            {"card": {"type": "object", "properties": {"iin": {"type": "string"}}}},
            {"card": {"type": "object", "properties": {}}},
        )
        kinds = [c.kind for c in changes]
        self.assertIn("response_field_removed", kinds)
        removed = [c for c in changes if c.kind == "response_field_removed"][0]
        self.assertEqual(removed.pointer, "paths./a.get.responses.200.card.iin")


class TestEnumChanges(unittest.TestCase):
    def test_enum_value_removed_is_breaking(self):
        old = make_spec([("/a", "post", op(resp_enums={"status": ["ok", "pending"]}))])
        new = make_spec([("/a", "post", op(resp_enums={"status": ["ok"]}))])
        changes = diff_specs(old, new)
        self.assertEqual(changes[0].kind, "enum_value_removed")
        self.assertEqual(changes[0].severity, "BREAKING")
        self.assertEqual(changes[0].old, "pending")

    def test_enum_value_added_is_not_flagged(self):
        old = make_spec([("/a", "post", op(resp_enums={"status": ["ok"]}))])
        new = make_spec([("/a", "post", op(resp_enums={"status": ["ok", "pending"]}))])
        changes = diff_specs(old, new)
        self.assertFalse([c for c in changes if c.severity == "BREAKING"])


class TestRequestChanges(unittest.TestCase):
    def test_new_required_request_field_is_breaking(self):
        old = make_spec([("/r", "post", op(req_required=["amount"]))])
        new = make_spec([("/r", "post", op(req_required=["amount", "reason"]))])
        changes = diff_specs(old, new)
        self.assertEqual(changes[0].kind, "request_required_added")
        self.assertEqual(changes[0].severity, "BREAKING")


class TestRefResolution(unittest.TestCase):
    def test_local_ref_resolved(self):
        spec_old = {
            "info": {"title": "T", "version": "1"},
            "paths": {"/a": {"get": {
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Thing"}}}}}}}},
            "components": {"schemas": {"Thing": {
                "type": "object", "properties": {"x": {"type": "string"}}}}},
        }
        spec_new = {
            "info": {"title": "T", "version": "2"},
            "paths": {"/a": {"get": {
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Thing"}}}}}}}},
            "components": {"schemas": {"Thing": {
                "type": "object", "properties": {}}}},
        }
        changes = diff_specs(spec_old, spec_new)
        self.assertEqual(changes[0].kind, "response_field_removed")

    def test_circular_ref_does_not_hang(self):
        circular = {
            "info": {"title": "T", "version": "1"},
            "paths": {"/a": {"get": {
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Node"}}}}}}}},
            "components": {"schemas": {"Node": {
                "type": "object",
                "properties": {"next": {"$ref": "#/components/schemas/Node"}}}}},
        }
        changes = diff_specs(circular, circular)  # must terminate
        self.assertEqual(changes, [])


class TestSummary(unittest.TestCase):
    def test_counts(self):
        old = make_spec([
            ("/gone", "get", op()),
            ("/a", "get", op(resp_props={"x": {"type": "string"}})),
        ])
        new = make_spec([
            ("/a", "get", op(resp_props={"x": {"type": "string"}})),
            ("/new", "post", op()),
        ])
        s = summarize(diff_specs(old, new))
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["breaking"], 1)
        self.assertEqual(s["additive"], 1)


class TestRealStripeReport(unittest.TestCase):
    """The committed report must keep matching the published numbers."""

    def test_committed_report_numbers(self):
        report_path = (Path(__file__).resolve().parent.parent
                       / "examples" / "stripe" / "stripe-diff-report.json")
        if not report_path.exists():
            self.skipTest("report not generated yet")
        import json
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["total"], 6398)
        self.assertEqual(report["summary"]["breaking"], 18)
        self.assertEqual(report["summary"]["additive"], 6380)
        iin = [c for c in report["changes"]
               if c["kind"] == "response_field_removed" and "card.iin" in c["pointer"]]
        self.assertEqual(len(iin), 2)  # POST /v1/tokens + GET /v1/tokens/{token}


if __name__ == "__main__":
    unittest.main()
