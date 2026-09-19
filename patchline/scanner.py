"""Patchline codebase scanner: map spec changes to consumer call sites.

v1 approach: pattern-based static scan (honest heuristic, documented as such).
Each change kind carries search patterns; we grep the consumer repo line by
line and record (file, line, matched_text, change_pointer).

In production this layer is an agent with full AST + type information; the
pattern scan is the deterministic v1 that already covers the common cases:
endpoint path literals, dotted field access, enum string comparisons.
"""
import os
import re
import json
from dataclasses import dataclass, asdict

DEFAULT_EXTENSIONS = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".py")
EXCLUDED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
SUPPORTED_BREAKING_KINDS = {
    "endpoint_removed", "response_removed", "request_body_required",
    "request_parameter_required", "request_media_removed", "response_type_changed",
    "response_field_removed", "enum_value_removed", "request_required_added",
}


@dataclass
class CallSite:
    file: str
    line: int
    code: str
    change_pointer: str
    change_kind: str

    def to_dict(self):
        return asdict(self)


def _patterns_for(change):
    """Yield regex patterns that indicate a call site affected by this change."""
    pats = []
    kind = change.kind
    path = change.path

    if kind in ("endpoint_removed", "response_removed", "request_body_required",
                "request_parameter_required", "request_media_removed", "request_required_added") or (
                    kind == "response_type_changed" and change.pointer.endswith((".$", ".[]"))):
        # template-literal `/v1/charges/${id}` and literal `/v1/charges/ch_123`
        dyn = r"(?:\$\{[^}]+\}|\w+)"
        pat = re.escape(path)
        pat = re.sub(r"\\\{[^}]+\\\}", lambda _m: dyn, pat)  # un-escape {param} into dynamic matcher
        pats.append(pat)
        prefix = path.split("{")[0]
        if "{" in path and prefix != "/":
            pats.append(re.escape(prefix))
    if kind in ("response_type_changed", "response_field_removed") and not change.pointer.endswith(".$"):
        ptr = re.split(r"\.responses\.(?:[1-5][0-9]{2}|[1-5]XX|default)\.(?:content\[[^]]*\]\.)?",
                       change.pointer, maxsplit=1)[-1]
        ptr = ptr.replace("[]", "")
        parts = [p for p in ptr.split(".") if p]
        if parts:
            pats.append(r"\." + re.escape(parts[-1]) + r"\b")           # .address
            pats.append(r"\[\s*['\"]" + re.escape(parts[-1]) + r"['\"]\s*\]")
            if len(parts) >= 2:
                pats.append(re.escape(parts[-2]) + r"\." + re.escape(parts[-1]))
    if kind == "enum_value_removed":
        pats.append(r"['\"`]" + re.escape(str(change.old)) + r"['\"`]")
        if not isinstance(change.old, str):
            pats.append(r"(?<![\w.])" + re.escape(json.dumps(change.old)) + r"(?![\w.])")
            if change.old is None or isinstance(change.old, bool):
                pats.append(r"(?<![\w.])" + re.escape(str(change.old)) + r"(?![\w.])")
    if kind == "request_required_added":
        pats.append(re.escape(path))                       # callers of that endpoint
        tail = path.rstrip("/").split("/")[-1]
        pats.append(re.escape(tail))                       # e.g. 'refunds'
    return [re.compile(p) for p in dict.fromkeys(pats)]


def scan_repo(repo_dir, changes, exts=DEFAULT_EXTENSIONS):
    if not os.path.isdir(repo_dir):
        raise ValueError(f"repository directory does not exist: {repo_dir}")
    sites = []
    breaking = [c for c in changes if c.severity == "BREAKING"]
    unsupported = sorted({c.kind for c in breaking} - SUPPORTED_BREAKING_KINDS)
    if unsupported:
        raise ValueError(f"unsupported breaking change kinds: {', '.join(unsupported)}")
    patterns = [(c, _patterns_for(c)) for c in breaking]
    def walk_error(error):
        raise error
    for root, dirs, files in os.walk(repo_dir, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS
                         and not os.path.islink(os.path.join(root, d)))
        for fn in sorted(files):
            if not fn.lower().endswith(exts):
                continue
            fp = os.path.join(root, fn)
            if os.path.islink(fp):
                continue
            rel = os.path.relpath(fp, repo_dir)
            with open(fp, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for change, pats in patterns:
                for i, line in enumerate(lines, 1):
                    if any(p.search(line) for p in pats):
                        sites.append(CallSite(
                            file=rel.replace(os.sep, "/"),
                            line=i, code=line.strip(),
                            change_pointer=change.pointer,
                            change_kind=change.kind))
    # de-dup identical (file, line, change_pointer)
    seen, out = set(), []
    for s in sites:
        key = (s.file, s.line, s.change_pointer, s.change_kind)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return sorted(out, key=lambda s: (s.file, s.line, s.change_pointer, s.change_kind))
