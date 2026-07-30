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
from dataclasses import dataclass, asdict


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

    if kind == "endpoint_removed":
        # template-literal `/v1/charges/${id}` and literal `/v1/charges/ch_123`
        dyn = r"(?:\$\{[^}]+\}|\w+)"
        pat = re.escape(path)
        pat = re.sub(r"\\\{[^}]+\\\}", lambda _m: dyn, pat)  # un-escape {param} into dynamic matcher
        pats.append(pat)
        pats.append(re.escape(path.split("{")[0]))  # path prefix, e.g. /v1/charges/
    if kind in ("response_type_changed", "response_field_removed"):
        ptr = change.pointer.split("responses.200.")[-1]
        parts = [p for p in ptr.split(".") if p]
        if parts:
            pats.append(r"\." + re.escape(parts[-1]) + r"\b")           # .address
            if len(parts) >= 2:
                pats.append(re.escape(parts[-2]) + r"\." + re.escape(parts[-1]))
    if kind == "enum_value_removed" and change.old:
        pats.append(r"['\"`]" + re.escape(str(change.old)) + r"['\"`]")
    if kind == "request_required_added":
        pats.append(re.escape(path))                       # callers of that endpoint
        tail = path.rstrip("/").split("/")[-1]
        pats.append(re.escape(tail))                       # e.g. 'refunds'
    return [re.compile(p) for p in dict.fromkeys(pats)]


def scan_repo(repo_dir, changes, exts=(".js", ".ts", ".jsx", ".tsx")):
    sites = []
    breaking = [c for c in changes if c.severity == "BREAKING"]
    for root, _dirs, files in os.walk(repo_dir):
        for fn in files:
            if not fn.endswith(exts):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, repo_dir)
            with open(fp, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for change in breaking:
                pats = _patterns_for(change)
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
        key = (s.file, s.line, s.change_pointer)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out
