"""Patchline — open-source API change detection.

Diff two OpenAPI specs, classify every change as BREAKING or ADDITIVE,
and map breaking changes to the exact call sites in a consumer codebase.
"""
from .spec_diff import Change, load_spec, diff_specs, summarize
from .scanner import CallSite, scan_repo

__version__ = "0.2.0"
__all__ = ["Change", "CallSite", "load_spec", "diff_specs", "summarize", "scan_repo"]
