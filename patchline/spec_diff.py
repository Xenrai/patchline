"""Patchline spec differ: diff two OpenAPI (JSON) specs and classify changes.

Supports real-world specs (Stripe etc.): OpenAPI 3 `content` wrappers and
local $ref resolution with cycle/depth guards. Falls back to the simplified
inline `schema` shape used by the demo fixtures.

Classification rules (deterministic):
  BREAKING:  endpoint removed | response property removed | response property
             type changed | requestBody required property added | enum value removed
             | response removed | required body/parameter | request media removed
  ADDITIVE:  endpoint added | response added | response property added
  REVIEW:    schema composition changed; compatibility is not established
"""
import json
import re
from urllib.parse import unquote
from dataclasses import dataclass, asdict

MAX_DEPTH = 5


@dataclass
class Change:
    kind: str
    severity: str        # BREAKING | REVIEW | ADDITIVE
    path: str
    method: str
    detail: str
    pointer: str
    old: object = None
    new: object = None

    def to_dict(self):
        return asdict(self)


def load_spec(p):
    with open(p, "r", encoding="utf-8-sig") as f:
        spec = json.load(f)
    _validate_spec(spec)
    return spec


def _validate_spec(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise ValueError("spec must be a JSON object containing a 'paths' object")
    if "info" in spec and not isinstance(spec["info"], dict):
        raise ValueError("spec 'info' must be an object")


def _operations(spec):
    ops = {}
    for path, item in spec.get("paths", {}).items():
        if not isinstance(path, str) or not path.startswith("/"):
            if isinstance(path, str) and path.startswith("x-"):
                continue
            raise ValueError("operation paths must start with '/'")
        if not isinstance(item, dict):
            raise ValueError(f"path item {path!r} must be an object")
        item = _resolve(spec, item)
        for method, op in item.items():
            if method.lower() in (
                    "get", "post", "put", "delete", "patch", "head", "options", "trace"):
                if not isinstance(op, dict):
                    raise ValueError(f"{method.upper()} {path} must be an object")
                op = dict(op)
                inherited = item.get("parameters", [])
                local = op.get("parameters", [])
                if not isinstance(inherited, list) or not isinstance(local, list):
                    raise ValueError(f"parameters for {path} must be arrays")
                op["parameters"] = inherited + local
                ops[(path, method.lower())] = op
    return ops


def _resolve(spec, node, seen=None):
    """Resolve local $refs one hop at a time (cycle-guarded)."""
    if node is not None and not isinstance(node, dict):
        raise ValueError("schema and reference definitions must be objects")
    seen = set(seen or ())
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise ValueError(f"unsupported reference {ref!r}; use local '#/' references")
        if ref in seen:
            return {}
        seen.add(ref)
        target = spec
        for part in unquote(ref[2:]).split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                raise ValueError(f"unresolved reference {ref!r}")
            target = target[part]
        if not isinstance(target, dict):
            raise ValueError(f"reference {ref!r} must resolve to an object")
        node = target
    return node if isinstance(node, dict) else {}


def _request_schemas(spec, body):
    content = body.get("content", {})
    if not isinstance(content, dict):
        raise ValueError("request content must be an object")
    if not content:
        return {"": body}
    schemas = {}
    for media, value in sorted(content.items()):
        if not isinstance(value, dict):
            raise ValueError("media type definitions must be objects")
        schemas[media] = _resolve(spec, value.get("schema"))
    return schemas


def _required(schema):
    required = schema.get("required", [])
    if isinstance(required, bool):  # legacy inline requestBody shape
        return set()
    if not isinstance(required, list) or not all(isinstance(v, str) for v in required):
        raise ValueError("schema required must be an array of property names")
    return set(required)


def _schema_type(schema):
    value = schema.get("type", "any")
    values = value if isinstance(value, list) else [value]
    if not all(isinstance(v, str) for v in values):
        raise ValueError("schema type must be a string or an array of strings")
    if schema.get("nullable") is True and "any" not in values:
        values = [*values, "null"]
    return "|".join(sorted(set(values)))


def _props(spec, schema, prefix="", depth=0):
    out = {}
    if depth > MAX_DEPTH:
        return out
    schema = _resolve(spec, schema)
    props = schema.get("properties")
    if props is not None and not isinstance(props, dict):
        raise ValueError("schema properties must be an object")
    if isinstance(props, dict):
        for name, sub in props.items():
            ptr = f"{prefix}.{name}" if prefix else name
            sub_r = _resolve(spec, sub)
            out[ptr] = _schema_type(sub_r)
            out.update(_props(spec, sub_r, ptr, depth + 1))
    if "items" in schema:
        item = _resolve(spec, schema["items"])
        ptr = prefix + "[]"
        out[ptr] = _schema_type(item)
        out.update(_props(spec, item, ptr, depth + 1))
    return out


def _enums(spec, schema, prefix="", depth=0):
    out = {}
    if depth > MAX_DEPTH:
        return out
    schema = _resolve(spec, schema)
    if isinstance(schema.get("enum"), list):
        out[prefix or "$"] = schema["enum"]
    props = schema.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            ptr = f"{prefix}.{name}" if prefix else name
            sub_r = _resolve(spec, sub)
            if "enum" in sub_r and isinstance(sub_r["enum"], list):
                out[ptr] = sub_r["enum"]
            out.update(_enums(spec, sub_r, ptr, depth + 1))
    if "items" in schema:
        out.update(_enums(spec, schema["items"], prefix + "[]", depth + 1))
    return out


def _compositions(spec, schema, prefix="", depth=0):
    """Locate unsupported compositions without inventing field removals."""
    if depth > MAX_DEPTH:
        return {}
    schema = _resolve(spec, schema)
    composed = {key: schema[key] for key in ("allOf", "oneOf", "anyOf") if key in schema}
    if composed:
        return {prefix: composed}
    found = {}
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for name, child in properties.items():
            pointer = f"{prefix}.{name}" if prefix else name
            found.update(_compositions(spec, child, pointer, depth + 1))
    if "items" in schema:
        found.update(_compositions(spec, schema["items"], prefix + "[]", depth + 1))
    return found


def _diff_response(old_spec, new_spec, old_schema, new_schema, path, method, base):
    changes = []
    old_composed = _compositions(old_spec, old_schema)
    new_composed = _compositions(new_spec, new_schema)
    old_props = _props(old_spec, old_schema)
    new_props = _props(new_spec, new_schema)
    candidates = {p for p in old_composed.keys() | new_composed.keys()
                  if not p or p in old_props and p in new_props}
    blocked = {p for p in candidates if not any(
        parent != p and (not parent or p.startswith((parent + ".", parent + "[]")))
        for parent in candidates)}

    def covered(pointer):
        return not any(not p or pointer == p or pointer.startswith((p + ".", p + "[]")) for p in blocked)

    for pointer in sorted(blocked):
        if old_composed.get(pointer) != new_composed.get(pointer):
            changes.append(Change(
                kind="response_schema_composition_changed", severity="REVIEW", path=path, method=method,
                detail="Schema composition changed; manual compatibility review required",
                pointer=f"{base}.{pointer or '$'}", old=old_composed.get(pointer),
                new=new_composed.get(pointer)))
    old_props = {p: t for p, t in old_props.items() if covered(p)}
    new_props = {p: t for p, t in new_props.items() if covered(p)}
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

    old_enums = _enums(old_spec, old_schema)
    new_enums = _enums(new_spec, new_schema)
    for ptr, old_vals in sorted(old_enums.items()):
        if not covered(ptr):
            continue
        new_vals = new_enums.get(ptr)
        if new_vals is None:
            continue
        new_keys = {json.dumps(v, sort_keys=True) for v in new_vals}
        for removed in sorted(old_vals, key=lambda v: json.dumps(v, sort_keys=True)):
            if json.dumps(removed, sort_keys=True) in new_keys:
                continue
            changes.append(Change(
                kind="enum_value_removed", severity="BREAKING", path=path, method=method,
                detail=f"Enum value '{removed}' removed from '{ptr}'",
                pointer=f"{base}.{ptr}", old=removed))

    return changes


def _response_variants(spec, op):
    """Keep status/media variants separate so changes cannot mask each other."""
    responses = op.get("responses", {})
    if not isinstance(responses, dict):
        raise ValueError("responses must be an object")
    variants = {}
    for status, node in sorted(responses.items()):
        if status.startswith("x-"):
            continue
        if not re.fullmatch(r"(?:[1-5][0-9]{2}|[1-5]XX|default)", status):
            raise ValueError(f"invalid response status {status!r}")
        resp = _resolve(spec, node)
        content = resp.get("content", {})
        if not isinstance(content, dict):
            raise ValueError("response content must be an object")
        if content:
            for media, value in sorted(content.items()):
                if not isinstance(value, dict):
                    raise ValueError("media type definitions must be objects")
                variants[(status, media)] = _resolve(spec, value.get("schema"))
        else:
            variants[(status, "")] = _resolve(spec, resp.get("schema"))
    return variants


def _parameters(spec, op):
    result = {}
    for node in op.get("parameters", []):
        param = _resolve(spec, node)
        if not isinstance(param.get("name"), str) or param.get("in") not in (
                "path", "query", "header", "cookie"):
            raise ValueError("parameters need a name and a valid 'in' location")
        result[(param["in"], param["name"])] = param
    return result


def diff_specs(old_spec, new_spec):
    """Compare supported OpenAPI contracts; raise ValueError for invalid input.

    Changes retain the original fields and add the REVIEW severity in v0.3.
    Media types are included in pointers
    when more than one representation is present for a response status.
    """
    _validate_spec(old_spec)
    _validate_spec(new_spec)
    old_ops, new_ops = _operations(old_spec), _operations(new_spec)
    changes = []
    for key in sorted(old_ops.keys() | new_ops.keys()):
        path, method = key
        base = f"paths.{path}.{method}"
        def add(kind, pointer, detail, old=None, new=None, severity="BREAKING"):
            changes.append(Change(kind, severity, path, method, detail, pointer, old, new))
        if key not in new_ops:
            add("endpoint_removed", base, f"{method.upper()} {path} was removed")
            continue
        if key not in old_ops:
            add("endpoint_added", base, f"{method.upper()} {path} was added", severity="ADDITIVE")
            continue
        old_op, new_op = old_ops[key], new_ops[key]
        old_variants = _response_variants(old_spec, old_op)
        new_variants = _response_variants(new_spec, new_op)
        for status, media in sorted(old_variants.keys() | new_variants.keys()):
            variant = status, media
            representations = {m for s, m in old_variants.keys() | new_variants.keys() if s == status}
            response_base = f"{base}.responses.{status}"
            if len(representations) > 1:
                response_base += f".content[{media}]"
            if variant not in new_variants:
                add("response_removed", response_base, f"Response {status} {media} removed")
                continue
            if variant not in old_variants:
                add("response_added", response_base, f"Response {status} {media} added", severity="ADDITIVE")
                continue
            old_schema, new_schema = old_variants[variant], new_variants[variant]
            composed_root = any(k in old_schema or k in new_schema for k in ("allOf", "oneOf", "anyOf"))
            if not composed_root and _schema_type(old_schema) != _schema_type(new_schema):
                add("response_type_changed", response_base + ".$",
                    f"Response {status} root type changed", _schema_type(old_schema),
                    _schema_type(new_schema))
            changes.extend(_diff_response(old_spec, new_spec, old_schema, new_schema,
                                          path, method, response_base))
        old_body = _resolve(old_spec, old_op.get("requestBody", {}))
        new_body = _resolve(new_spec, new_op.get("requestBody", {}))
        old_requests = _request_schemas(old_spec, old_body)
        new_requests = _request_schemas(new_spec, new_body)
        for media, schema in sorted(new_requests.items()):
            # Adding an alternative content type imposes no new obligations
            # on callers of an existing representation.
            if media not in old_requests and old_body:
                continue
            old_required = _required(old_requests.get(media, {}))
            for name in sorted(_required(schema) - old_required):
                request_base = base + ".requestBody"
                if len(old_requests.keys() | new_requests.keys()) > 1:
                    request_base += f".content[{media}]"
                properties = schema.get("properties", {})
                if not isinstance(properties, dict):
                    raise ValueError("schema properties must be an object")
                prop = _resolve(new_spec, properties.get(name, {}))
                add("request_required_added", request_base + "." + name,
                    f"New required request field '{name}' on {method.upper()} {path}",
                    new=_schema_type(prop))
        for media in sorted(old_requests.keys() - new_requests.keys()):
            if old_body and media:
                add("request_media_removed", base + f".requestBody.content[{media}]",
                    f"Request media type '{media}' removed")
        if new_body.get("required") is True and old_body.get("required") is not True:
            add("request_body_required", base + ".requestBody", "Request body became required")
        old_params, new_params = _parameters(old_spec, old_op), _parameters(new_spec, new_op)
        for param_key, param in sorted(new_params.items()):
            previous = old_params.get(param_key, {})
            if param.get("required") is True and previous.get("required") is not True:
                location, name = param_key
                add("request_parameter_required", f"{base}.parameters.{location}.{name}",
                    f"New required {location} parameter '{name}'")
    return changes


def summarize(changes):
    breaking = [c for c in changes if c.severity == "BREAKING"]
    additive = [c for c in changes if c.severity == "ADDITIVE"]
    return {
        "total": len(changes),
        "breaking": len(breaking),
        "review": sum(c.severity == "REVIEW" for c in changes),
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
