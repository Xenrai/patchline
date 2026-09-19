"""Patchline — open-source API change detection.

Diff supported OpenAPI changes as BREAKING, REVIEW, or ADDITIVE,
and suggest potentially affected source locations in a consumer codebase.
"""
from .spec_diff import Change, load_spec, diff_specs, summarize
from .scanner import CallSite, scan_repo

__version__ = "0.3.0"
__all__ = ["Change", "CallSite", "load_spec", "diff_specs", "summarize", "scan_repo"]
