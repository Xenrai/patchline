"""Regression coverage for real contracts and command-line failure modes."""
import copy
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from patchline.cli import main
from patchline.scanner import scan_repo
from patchline.spec_diff import Change, diff_specs


def spec(schema=None, status="200", media="application/json", method="get"):
    return {"paths": {"/items": {method: {"responses": {
        status: {"content": {media: {"schema": schema or {}}}}
    }}}}}


def props(**fields):
    return {"type": "object", "properties": fields}


class ContractRegressions(unittest.TestCase):
    def test_object_becoming_union_does_not_invent_field_removals(self):
        old = spec(props(id={"type": "string"}, status={"type": "string"}))
        new = spec({"anyOf": [props(id={"type": "string"}), props(deleted={"type": "boolean"})]})
        changes = diff_specs(old, new)
        self.assertEqual([c.kind for c in changes], ["response_schema_composition_changed"])
        self.assertIn("manual compatibility review", changes[0].detail)
        self.assertEqual(changes[0].severity, "REVIEW")

    def test_new_composed_field_is_additive(self):
        changes = diff_specs(spec(props()), spec(props(result={"oneOf": [{"type": "string"}]})))
        self.assertEqual([c.kind for c in changes], ["response_field_added"])

    def test_parent_composition_suppresses_nested_noise(self):
        old = spec(props(result={"oneOf": [{"type": "string"}]}))
        new = spec({"anyOf": [props(result={"type": "string"})]})
        self.assertEqual(len(diff_specs(old, new)), 1)

    def test_nested_composition_change_preserves_other_findings(self):
        old = spec(props(result=props(id={"type": "string"}), extra={"type": "string"}))
        new = spec(props(result={"oneOf": [props(id={"type": "string"})]}))
        changes = diff_specs(old, new)
        removed = [c.pointer for c in changes if c.kind == "response_field_removed"]
        self.assertEqual(removed, ["paths./items.get.responses.200.extra"])
        self.assertIn("response_schema_composition_changed", [c.kind for c in changes])

    def test_unchanged_composition_does_not_create_findings(self):
        value = spec({"allOf": [props(id={"type": "string"})]})
        self.assertEqual(diff_specs(value, value), [])

    def test_all_response_statuses(self):
        for status in ("201", "204", "400", "2XX", "default"):
            with self.subTest(status=status):
                changes = diff_specs(spec(props(id={"type": "string"}), status), spec(props(), status))
                self.assertEqual([c.kind for c in changes], ["response_field_removed"])
                self.assertTrue(changes[0].pointer.endswith(f"responses.{status}.id"))

    def test_response_reference_and_escaped_pointer(self):
        old = spec()
        old["paths"]["/items"]["get"]["responses"]["200"] = {"$ref": "#/components/responses/A~1B~0C"}
        old["components"] = {"responses": {"A/B~C": {"schema": props(id={"type": "string"})}}}
        new = copy.deepcopy(old)
        new["components"]["responses"]["A/B~C"]["schema"] = props()
        self.assertEqual(diff_specs(old, new)[0].kind, "response_field_removed")

    def test_unresolved_and_external_references_fail(self):
        for ref in ("#/missing", "other.json#/Thing", 42):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                diff_specs(spec({"$ref": ref}), spec())

    def test_arrays_and_primitive_items(self):
        old = spec({"type": "array", "items": props(id={"type": "string"})})
        new = spec({"type": "array", "items": props()})
        self.assertEqual(diff_specs(old, new)[0].pointer, "paths./items.get.responses.200.[].id")
        changes = diff_specs(spec({"type": "array", "items": {"type": "integer"}}),
                             spec({"type": "array", "items": {"type": "string"}}))
        self.assertEqual(changes[0].kind, "response_type_changed")

    def test_primitive_root_type(self):
        changes = diff_specs(spec({"type": "string"}), spec({"type": "object"}))
        self.assertEqual(changes[0].pointer, "paths./items.get.responses.200.$")

    def test_union_order_is_not_a_change(self):
        self.assertEqual(diff_specs(spec({"type": ["string", "null"]}),
                                    spec({"type": ["null", "string"]})), [])

    def test_nullable_response_field(self):
        changes = diff_specs(spec(props(id={"type": "string"})),
                             spec(props(id={"type": "string", "nullable": True})))
        self.assertEqual(changes[0].kind, "response_type_changed")

    def test_required_fields_in_each_request_representation(self):
        old = spec()
        old["paths"]["/items"]["get"]["requestBody"] = {"content": {
            "application/json": {"schema": props()},
            "multipart/form-data": {"schema": props(file={"type": "string"})}}}
        new = copy.deepcopy(old)
        new["paths"]["/items"]["get"]["requestBody"]["content"]["multipart/form-data"]["schema"]["required"] = ["file"]
        changes = diff_specs(old, new)
        self.assertEqual(len(changes), 1)
        self.assertIn("content[multipart/form-data].file", changes[0].pointer)

    def test_request_media_removal(self):
        old = spec()
        old["paths"]["/items"]["get"]["requestBody"] = {"content": {
            "application/json": {"schema": props()}}}
        self.assertEqual(diff_specs(old, spec())[0].kind, "request_media_removed")

    def test_media_types_compared_independently(self):
        old = spec(props(id={"type": "string"}))
        old["paths"]["/items"]["get"]["responses"]["200"]["content"]["application/problem+json"] = {
            "schema": props(message={"type": "string"})}
        new = copy.deepcopy(old)
        new["paths"]["/items"]["get"]["responses"]["200"]["content"]["application/problem+json"]["schema"] = props()
        changes = diff_specs(old, new)
        self.assertEqual(len(changes), 1)
        self.assertIn("content[application/problem+json].message", changes[0].pointer)

    def test_status_removal_without_body(self):
        old = spec(status="204")
        new = {"paths": {"/items": {"get": {"responses": {}}}}}
        self.assertEqual(diff_specs(old, new)[0].kind, "response_removed")

    def test_all_http_methods(self):
        for method in ("head", "options", "trace"):
            with self.subTest(method=method):
                changes = diff_specs(spec(method=method), {"paths": {}})
                self.assertEqual(changes[0].kind, "endpoint_removed")

    def test_required_parameter_inheritance_and_override(self):
        old = spec()
        new = copy.deepcopy(old)
        new["paths"]["/items"]["parameters"] = [{"name": "token", "in": "header", "required": True}]
        self.assertEqual(diff_specs(old, new)[0].kind, "request_parameter_required")
        new["paths"]["/items"]["get"]["parameters"] = [{"name": "token", "in": "header", "required": False}]
        self.assertEqual(diff_specs(old, new), [])

    def test_required_body_reference(self):
        old = spec()
        new = copy.deepcopy(old)
        new["components"] = {"requestBodies": {"Input": {"required": True}}}
        new["paths"]["/items"]["get"]["requestBody"] = {"$ref": "#/components/requestBodies/Input"}
        self.assertEqual(diff_specs(old, new)[0].kind, "request_body_required")

    def test_enum_type_changes_and_typed_values(self):
        changes = diff_specs(spec(props(value={"type": "integer", "enum": [1]})),
                             spec(props(value={"type": "string", "enum": ["1"]})))
        self.assertEqual({c.kind for c in changes}, {"response_type_changed", "enum_value_removed"})
        self.assertIsInstance(next(c.old for c in changes if c.kind == "enum_value_removed"), int)

    def test_invalid_spec_not_silently_clean(self):
        for invalid in ([], {}, {"paths": []}, {"paths": {"/items": None}},
                        {"paths": {"/items": {"get": []}}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                diff_specs(invalid, {"paths": {}})

    def test_diff_does_not_modify_inputs(self):
        old = spec(props(value={"enum": [False, 0, ""]}))
        snapshot = copy.deepcopy(old)
        self.assertEqual(diff_specs(old, old), [])
        self.assertEqual(old, snapshot)


class ScannerRegressions(unittest.TestCase):
    def change(self, kind="response_field_removed", old=None):
        return Change(kind, "BREAKING", "/items", "get", "test",
                      "paths./items.get.responses.201.content[application/json].id", old)

    def test_missing_repo_is_error(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            scan_repo(Path(temp) / "missing", [])

    def test_ignored_folders_and_python_bracket_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "client.py").write_text('return row["id"]\n', encoding="utf-8")
            for folder in ("node_modules", ".git", ".venv", "dist"):
                (root / folder).mkdir()
                (root / folder / "vendor.js").write_text("row.id\n", encoding="utf-8")
            sites = scan_repo(root, [self.change()])
            self.assertEqual([(s.file, s.line) for s in sites], [("client.py", 1)])

    def test_empty_and_zero_enum_values(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "a.js").write_text('const a = "";\nconst b = 0;\n', encoding="utf-8")
            self.assertEqual(scan_repo(temp, [self.change("enum_value_removed", "")])[0].line, 1)
            self.assertEqual(scan_repo(temp, [self.change("enum_value_removed", 0)])[0].line, 2)

    def test_deterministic_order(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ("z.ts", "b.mjs", "a.py"):
                (Path(temp) / name).write_text("row.id\n", encoding="utf-8")
            self.assertEqual([s.file for s in scan_repo(temp, [self.change()])], ["a.py", "b.mjs", "z.ts"])

    def test_unsupported_kind_cannot_pass_clean(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            scan_repo(temp, [self.change("future_breaking_kind")])

    def test_null_enum_and_root_array_type(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "a.js").write_text('fetch("/items");\nconst value = null;\n', encoding="utf-8")
            c = self.change("response_type_changed")
            c.pointer = "paths./items.get.responses.200.[]"
            self.assertEqual(scan_repo(temp, [c])[0].line, 1)
            self.assertEqual(scan_repo(temp, [self.change("enum_value_removed", None)])[0].line, 2)


class CliRegressions(unittest.TestCase):
    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = main(args)
        return result, out.getvalue(), err.getvalue()

    def test_bad_inputs_return_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            for content in ("{bad", "[]", "{}"):
                path.write_text(content, encoding="utf-8")
                result, _, err = self.invoke(["diff", str(path), str(path)])
                self.assertEqual(result, 2)
                self.assertIn("patchline: error:", err)
                self.assertNotIn("Traceback", err)

    def test_manual_review_fails_diff_gate_and_can_be_scanned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new, report = (root / name for name in ("old.json", "new.json", "report.json"))
            old.write_text(json.dumps(spec(props(id={"type": "string"}))), encoding="utf-8")
            new.write_text(json.dumps(spec({"anyOf": [props(id={"type": "string"})]})), encoding="utf-8")
            (root / "client.py").write_text('client.get("/items")\n', encoding="utf-8")
            status, out, _ = self.invoke(["diff", str(old), str(new), "--out", str(report)])
            self.assertEqual(status, 1)
            self.assertIn("0 BREAKING, 1 review", out)
            parsed = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(parsed["changes"][0]["severity"], "REVIEW")
            self.assertEqual(self.invoke(["scan", "--repo", temp, "--report", str(report)])[0], 1)

    def test_invalid_reports_return_two(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            for report in ([], {}, {"changes": [None]}, {"changes": [{}]},
                           {"changes": [{**ScannerRegressions().change().to_dict(), "severity": "BORKED"}]}):
                path.write_text(json.dumps(report), encoding="utf-8")
                result, _, err = self.invoke(["scan", "--repo", temp, "--report", str(path)])
                self.assertEqual(result, 2, report)
                self.assertIn("error:", err)

    def test_diff_scan_end_to_end_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new, report = (root / name for name in ("old.json", "new.json", "report.json"))
            old.write_text(json.dumps(spec(props(id={"type": "string"}), status="201")), encoding="utf-8")
            new.write_text(json.dumps(spec(props(), status="201")), encoding="utf-8")
            (root / "client.py").write_text('row["id"]\n', encoding="utf-8")
            self.assertEqual(self.invoke(["diff", str(old), str(new), "--out", str(report)])[0], 1)
            self.assertEqual(self.invoke(["scan", "--repo", temp, "--report", str(report)])[0], 1)
            self.assertEqual(self.invoke(["diff", str(old), str(old), "--out", str(report)])[0], 0)
            self.assertEqual(self.invoke(["scan", "--repo", temp, "--report", str(report)])[0], 0)

    def test_module_entrypoint(self):
        result = subprocess.run([sys.executable, "-m", "patchline", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("scan", result.stdout)


if __name__ == "__main__":
    unittest.main()
