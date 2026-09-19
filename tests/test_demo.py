import contextlib
import io
import json
import unittest
from importlib.resources import files
from unittest.mock import patch

from patchline import __version__
from patchline.cli import main


class DemoTests(unittest.TestCase):
    def test_demo_runs_real_comparison_offline(self):
        output = io.StringIO()
        with patch("socket.socket", side_effect=AssertionError("demo must be offline")):
            with contextlib.redirect_stdout(output):
                result = main(["demo"])
        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn("4 breaking changes -> 4 potential call sites", text)
        for location in ("billing.js:2", "billing.js:9", "billing.js:13", "refunds.js:3"):
            self.assertIn(location, text)

    def test_demo_specs_use_openapi_content_wrappers(self):
        for name in ("before.json", "after.json"):
            spec = json.loads(files("patchline").joinpath("demo_data", name).read_text(encoding="utf-8"))
            for item in spec["paths"].values():
                for operation in item.values():
                    for response in operation["responses"].values():
                        self.assertIn("application/json", response["content"])
                    if "requestBody" in operation:
                        self.assertIn("application/json", operation["requestBody"]["content"])

    def test_version_works_without_subcommand(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exit_:
            main(["--version"])
        self.assertEqual(exit_.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), "patchline " + __version__)
