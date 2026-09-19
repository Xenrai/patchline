# patchline

Diff two OpenAPI specs, classify supported changes as breaking or additive, and map
the breaking ones to the potentially affected call sites in your codebase (file:line).

Python 3.10+, zero dependencies, no network access, no LLM calls. MIT.

## Why

Since 2024, Stripe ships breaking API changes twice a year through named
releases (acacia, basil, clover, dahlia) — documented in their own upgrade
guides. Most consumers find out when production breaks. I wanted a number for
how big the problem actually is, so I ran this tool on Stripe's real published
specs. The numbers below are that run, and you can reproduce them.

## The Stripe numbers (reproducible)

Source: `openapi/spec3.json` in [stripe/openapi](https://github.com/stripe/openapi),
release tags `v2250` (2026-04-22.dahlia) → `v2349` (2026-07-29.dahlia), ~8 MB each.

| | |
|---|---|
| Total changes | **6,398** |
| Breaking | **18** |
| Additive | 6,380 |

These v0.2 totals include array items and all response representations; they replace
the v0.1 totals of 679 changes (16 breaking). Findings are contract differences,
not a count of independent production failures.

The breaking set (full report: [`examples/stripe/stripe-diff-report.json`](examples/stripe/stripe-diff-report.json)):

- **`card.iin` removed, no replacement field** — from `POST /v1/tokens` and
  `GET /v1/tokens/{token}`. Code doing `token.card.iin.slice(0, 6)` for BIN
  routing compiles fine and dies at runtime.
- **`iin` removed from `GET /v1/customers/{customer}/cards/{id}`** — same field,
  second surface.
- **`data[].iin` removed** from the customer card list response, previously
  missed because it is inside an array.
- **Root response type changed** on the terminal reader cancel action.
- **13 fields removed from `POST /v1/terminal/readers/{reader}/cancel_action`** —
  the response object was restructured; every property a client might read
  (`serial_number`, `status`, `ip_address`, …) is gone.

Reproduce:

```bash
pip install -e .
python examples/stripe/run_stripe_diff.py
# downloads the two pinned specs (~16 MB), runs the diff, checks the numbers:
# expected {'total': 6398, 'breaking': 18, 'additive': 6380} -> MATCH
```

## Install

```bash
pip install -e .          # Python 3.10+, zero dependencies
```

## Quickstart

```bash
# 1. Diff two specs (writes a full JSON report)
patchline diff examples/pay_api_v1.json examples/pay_api_v2.json --out diff.json

# 2. Map the breaking changes to call sites in a repo
patchline scan --repo examples/consumer --report diff.json
```

Real output of step 2:

```
4 breaking changes -> 7 affected call site(s) in examples/consumer

  billing.js:2     [endpoint_removed] const CHARGE_URL = (id) => `/v1/charges/${id}`;
  billing.js:9     [enum_value_removed] return charge.status === "pending";
  billing.js:13    [response_type_changed] return charge.billing_details.address.split(",")[1].trim();
  mockClient.js:19    [request_required_added] if (path === "/v1/refunds") {
  refunds.js:3     [request_required_added] return client.post("/v1/refunds", { charge: chargeId, amount });
  test.js:5     [request_required_added] const refunds = require("./refunds");
  test.js:37    [request_required_added] const r = await refunds.refundCharge(client, "ch_123", 500);
```

Both commands exit `1` when breaking changes / affected call sites are found
and `0` when no supported findings are detected. Invalid input, missing folders,
unreadable files, and output-write failures exit `2` with an error on stderr.
Use these distinct codes in CI; a scan with zero matches does not prove compatibility.

## What it detects

| Class | Severity | Example |
|---|---|---|
| Endpoint removed | BREAKING | `GET /v1/charges/{id}` gone |
| Response field removed | BREAKING | `card.iin` no longer returned |
| Response type changed | BREAKING | `address`: string → object |
| Enum value removed | BREAKING | `status: "pending"` retired |
| Required request field added | BREAKING | `reason` now mandatory |
| Required body / parameter added | BREAKING | a header or body becomes mandatory |
| Response / media type removed | BREAKING | `201` or a content representation removed |
| Request media type removed | BREAKING | form encoding no longer accepted |
| Endpoint / response / field added | additive | informational |

Spec support: JSON OpenAPI documents, all eight HTTP methods, every response
status (including `default` and status ranges), separate media representations,
local `$ref` resolution with escaped JSON Pointer tokens, array items, root
response types, nullable types, and required top-level request fields across
content types. Path-level parameters are inherited, with operation-level overrides.
Broken or external references encountered during comparison produce an error.

## How it works

- `patchline/spec_diff.py` compares operations and response representations,
  walks nested properties and array items, and checks request requirements.
- `patchline/scanner.py` matches endpoint literals, dotted/bracket field access,
  and enum literals against source files. Patterns are compiled once per scan.
- `patchline/cli.py` provides `diff` and `scan`, JSON report files, and CI exit codes.

Scan results are sorted by file and line. Supported extensions are `.js`, `.ts`,
`.jsx`, `.tsx`, `.mjs`, `.cjs`, and `.py`. Dependency, build, cache, and Git folders
are excluded (`node_modules`, `.venv`, `venv`, `dist`, `build`, `__pycache__`, `.git`).
Symlinks are skipped. Source files must be UTF-8; unreadable source produces an error.

## Limitations

- This is a pattern scanner, not an AST or data-flow analyzer. It can both miss
  affected call sites and flag unrelated code. Review the matched file and line.
- Schema traversal is capped at five levels. Composition (`allOf`, `oneOf`,
  `anyOf`), discriminators, arbitrary additional properties, and full JSON Schema
  constraint compatibility are not analyzed.
- Request checking covers top-level required properties, required bodies and
  parameters, and removed media types. It does not compare nested request
  requirements, parameter types, authentication, or validation bounds.
- YAML, external references, callbacks, and webhooks are unsupported. Convert or
  bundle specs into JSON with local references first.
- Validation checks supported input shapes; it is not a complete OpenAPI validator.
- Response enum removals retain the original conservative breaking classification;
  enum additions are not reported. A type change is conservatively breaking.

## Tests

```bash
python -m unittest discover tests -v
```

Tests cover original fixtures, response variants, arrays, references, request
requirements, scanner exclusions, input failures, and end-to-end CLI exit codes.
The weekly workflow reruns the pinned Stripe comparison. Package discovery is
explicit so installation includes only `patchline`, not fixtures or tests.

## Open source vs. commercial

This repo is detection: diff, classify, call-site scan. The commercial product
adds remediation (rewrites affected call sites, opens a PR gated on your own
CI) and continuous watching of the APIs you depend on. If the detection core
is useful to you, issues and PRs are welcome — especially new change-class
patterns and scanner support for more languages.

## License

MIT — see [LICENSE](LICENSE).
