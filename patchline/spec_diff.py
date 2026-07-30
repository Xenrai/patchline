"""Patchline spec differ: diff two OpenAPI (JSON) specs and classify changes.

Supports real-world specs (Stripe etc.): OpenAPI 3 `content` wrappers and
local $ref resolution with cycle/depth guards. Falls back to the simplified
inline `schema` shape used by the demo fixtures.

Classification rules (v1, deterministic):
  BREAKING:  endpoint removed | response property removed | response property
             type changed | requestBody required property added | enum value removed
  ADDITIVE:  endpoint added | response property added
"""
import json
from dataclasses import dataclass, asdict

MAX_DEPTH = 5


@dataclass
class Change:
    kind: str
    severity: str        # BREAKING | ADDITIVE
    path: str
    method: str
    detail: str
    pointer: str
    old: object = None
    new: object = None

    def to_dict(self):
        return asdict(self)


def load_spec(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _operations(spec):
    ops = {}
    for path, item in spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if isinstance(op, dict) and method.lower() in (
                    "get", "post", "put", "delete", "patch"):
                ops[(path, method)] = op
    return ops


def _resolve(spec, node, seen=None):
    """Resolve local $refs one hop at a time (cycle-guarded)."""
    seen = seen or set()
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/") or ref in seen:
            return {}
        seen.add(ref)
        target = spec
        for part in ref[2:].split("/"):
            target = (target or {}).get(part)
            if target is None:
                return {}
        node = target
    return node if isinstance(node, dict) else {}


def _response_schema(spec, op):
    resp = op.get("responses", {}).get("200", {}) or {}
    content = resp.get("content") or {}
    for mt in ("application/json", "application/*+json"):
        if mt in content:
            return _resolve(spec, content[mt].get("schema"))
    if "schema" in resp:  # simplified demo shape
        return _resolve(spec, resp.get("schema"))
    return {}


def _request_schema(spec, op):
    rb = op.get("requestBody") or {}
    content = rb.get("content") or {}
    for mt in ("application/json", "application/x-www-form-urlencoded"):
        if mt in content:
            return _resolve(spec, content[mt].get("schema"))
    if "properties" in rb or "required" in rb:  # simplified demo shape
        return rb
    return {}


def _props(spec, schema, prefix="", depth=0):
    out = {}
    if depth > MAX_DEPTH:
        return out
    schema = _resolve(spec, schema)
    props = schema.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            ptr = f"{prefix}.{name}" if prefix else name
            sub_r = _resolve(spec, sub)
            t = sub_r.get("type", "any")
            if isinstance(t, list):
                t = "|".join(sorted(t))
            out[ptr] = t
            if "enum" in sub_r:
                out[ptr] = "enum"
            out.update(_props(spec, sub_r, ptr, depth + 1))
    return out


def _enums(spec, schema, prefix="", depth=0):
    out = {}
    if depth > MAX_DEPTH:
        return out
    schema = _resolve(spec, schema)
    props = schema.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            ptr = f"{prefix}.{name}" if prefix else name
            sub_r = _resolve(spec, sub)
            if "enum" in sub_r and isinstance(sub_r["enum"], list):
                out[ptr] = sorted(str(v) for v in sub_r["enum"])
            out.update(_enums(spec, sub_r, ptr, depth + 1))
    return out


def diff_specs(old_spec, new_spec):
    changes = []
    old_ops, new_ops = _operations(old_spec), _operations(new_spec)

    for (path, method) in sorted(old_ops):
        if (path, method) not in new_ops:
            changes.append(Change(
                kind="endpoint_removed", severity="BREAKING", path=path, method=method,
                detail=f"{method.upper()} {path} was removed",
                pointer=f"paths.{path}.{method}"))
    for (path, method) in sorted(new_ops):
        if (path, method) not in old_ops:
            changes.append(Change(
                kind="endpoint_added", severity="ADDITIVE", path=path, method=method,
                detail=f"{method.upper()} {path} was added",
                pointer=f"paths.{path}.{method}"))

    for (path, method) in sorted(old_ops):
        if (path, method) not in new_ops:
            continue
        old_props = _props(old_spec, _response_schema(old_spec, old_ops[(path, method)]))
        new_props = _props(new_spec, _response_schema(new_spec, new_ops[(path, method)]))
        base = f"paths.{path}.{method}.responses.200"
        for ptr in sorted(old_props):
            if ptr not in new_props:
                changes.append(Change(
                    kind="response_field_removed", severity="BREAKING", path=path, method=method,
                    detail=f"Response field '{ptr}' removed from {method.upper()} {path}",
                    pointer=f"{base}.{ptr}", old=old_props[ptr]))
            elif new_props[ptr] != old_props[ptr]:
                changes.append(Change(
                    kind="response_type_changed", severity="BREAKING", path=path, method=method,
                    detail=f"Response field '{ptr}' changed type {old_props[ptr]} -> {new_props[ptr]}",
                    pointer=f"{base}.{ptr}", old=old_props[ptr], new=new_props[ptr]))
        for ptr in sorted(new_props):
            if ptr not in old_props:
                changes.append(Change(
                    kind="response_field_added", severity="ADDITIVE", path=path, method=method,
                    detail=f"Response field '{ptr}' added",
                    pointer=f"{base}.{ptr}", new=new_props[ptr]))

        old_enums = _enums(old_spec, _response_schema(old_spec, old_ops[(path, method)]))
        new_enums = _enums(new_spec, _response_schema(new_spec, new_ops[(path, method)]))
        for ptr, old_vals in sorted(old_enums.items()):
            new_vals = new_enums.get(ptr)
            if new_vals is None:
                continue
            for removed in sorted(set(old_vals) - set(new_vals)):
                changes.append(Change(
                    kind="enum_value_removed", severity="BREAKING", path=path, method=method,
                    detail=f"Enum value '{removed}' removed from '{ptr}'",
                    pointer=f"{base}.{ptr}", old=removed))

        old_req = _request_schema(old_spec, old_ops[(path, method)])
        new_req = _request_schema(new_spec, new_ops[(path, method)])
        _req_list = lambda rb: set(rb.get("required")) if isinstance(rb.get("required"), list) else set()
        old_required = _req_list(old_req)
        new_required = _req_list(new_req)
        for name in sorted(new_required - old_required):
            prop = _resolve(new_spec, (new_req.get("properties") or {}).get(name, {}))
            changes.append(Change(
                kind="request_required_added", severity="BREAKING", path=path, method=method,
                detail=f"New required request field '{name}' on {method.upper()} {path}",
                pointer=f"paths.{path}.{method}.requestBody.{name}",
                new=prop.get("type", "any")))

    return changes


def summarize(changes):
    breaking = [c for c in changes if c.severity == "BREAKING"]
    additive = [c for c in changes if c.severity == "ADDITIVE"]
    return {
        "total": len(changes),
        "breaking": len(breaking),
        "additive": len(additive),
        "by_kind": {k: sum(1 for c in changes if c.kind == k)
                    for k in sorted({c.kind for c in changes})},
    }


if __name__ == "__main__":
    import sys
    old, new = load_spec(sys.argv[1]), load_spec(sys.argv[2])
    cs = diff_specs(old, new)
    print(json.dumps({"summary": summarize(cs),
                      "changes": [c.to_dict() for c in cs]}, indent=2))
