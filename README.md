# patchline

Diff two OpenAPI specs, classify every change as breaking or additive, and map
the breaking ones to the exact call sites in your codebase (file:line).

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
| Total changes | **679** |
| Breaking | **16** |
| Additive | 663 |
| Runtime of the diff itself | ~0.5 s |

The breaking set (full report: [`examples/stripe/stripe-diff-report.json`](examples/stripe/stripe-diff-report.json)):

- **`card.iin` removed, no replacement field** — from `POST /v1/tokens` and
  `GET /v1/tokens/{token}`. Code doing `token.card.iin.slice(0, 6)` for BIN
  routing compiles fine and dies at runtime.
- **`iin` removed from `GET /v1/customers/{customer}/cards/{id}`** — same field,
  second surface.
- **13 fields removed from `POST /v1/terminal/readers/{reader}/cancel_action`** —
  the response object was restructured; every property a client might read
  (`serial_number`, `status`, `ip_address`, …) is gone.

Reproduce:

```bash
pip install -e .
python examples/stripe/run_stripe_diff.py
# downloads the two pinned specs (~16 MB), runs the diff, checks the numbers:
# expected {'total': 679, 'breaking': 16, 'additive': 663} -> MATCH
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
  billing.js:13    [response_type_changed] return charge.billing_details.address.split(",")[1].trim();
  billing.js:9     [enum_value_removed] return charge.status === "pending";
  mockClient.js:19    [request_required_added] if (path === "/v1/refunds") {
  refunds.js:3     [request_required_added] return client.post("/v1/refunds", { charge: chargeId, amount });
  test.js:5     [request_required_added] const refunds = require("./refunds");
  test.js:37    [request_required_added] const r = await refunds.refundCharge(client, "ch_123", 500);
```

Both commands exit `1` when breaking changes / affected call sites are found
and `0` when clean, so they drop into CI as a dependency-drift gate.

## What it detects

| Class | Severity | Example |
|---|---|---|
| Endpoint removed | BREAKING | `GET /v1/charges/{id}` gone |
| Response field removed | BREAKING | `card.iin` no longer returned |
| Response type changed | BREAKING | `address`: string → object |
| Enum value removed | BREAKING | `status: "pending"` retired |
| Required request field added | BREAKING | `reason` now mandatory |
| Endpoint / field added | additive | informational |

Spec support: OpenAPI 3 `content` wrappers, local `$ref` resolution
(cycle- and depth-guarded), JSON and form-encoded request bodies. The Stripe
specs exercise all of this — they are ~8 MB of `$ref`s.

## How it works

- `patchline/spec_diff.py` — walks both specs, flattens response schemas to
  `dotted.path -> type` maps (depth-capped), and diffs operations, properties,
  enums, and required request fields. Deterministic; same inputs, same report.
- `patchline/scanner.py` — for each breaking change, generates regexes from
  the change kind (path literals incl. template params, dotted field access,
  enum string literals) and greps the consumer repo line by line.
- `patchline/cli.py` — `diff` and `scan` subcommands, JSON reports, CI exit codes.

## Limitations

- The scanner is a pattern heuristic, not an AST. It catches the common cases
  (path literals, `.field` access, enum comparisons) and it will both miss
  obfuscated call sites and flag occasional false positives. The pointer and
  matched line are always printed so you can judge each hit.
- Only the `200` response schema is compared.
- Response schemas are flattened 5 levels deep (`MAX_DEPTH`).
- Scanner targets JS/TS files (`.js`, `.ts`, `.jsx`, `.tsx`).

These are v1 trade-offs, not invisible failure modes — contributions that
close them are the most valuable ones.

## Tests

```bash
python -m unittest discover tests -v    # 19 tests, stdlib only
```

CI runs the unit tests, re-runs the toy example exactly as documented above,
and validates the committed Stripe report against the published numbers. A
weekly job re-runs the real-spec diff from scratch.

## Open source vs. commercial

This repo is detection: diff, classify, call-site scan. The commercial product
adds remediation (rewrites affected call sites, opens a PR gated on your own
CI) and continuous watching of the APIs you depend on. If the detection core
is useful to you, issues and PRs are welcome — especially new change-class
patterns and scanner support for more languages.

## License

MIT — see [LICENSE](LICENSE).
