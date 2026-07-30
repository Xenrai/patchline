# Patchline

**Diff API specs. Find what breaks your code. Before your customers do.**

API providers ship breaking changes constantly — Stripe alone ships them twice a
year via named releases, and an ex-AWS engineer attributes 30%+ of service downtime
to unnoticed external API/package changes. Patchline diffs two OpenAPI specs,
classifies every change as **BREAKING** or additive, and maps breaking changes to
the exact call sites in your codebase (file:line).

No API keys, no LLM calls, no network access. Deterministic, MIT-licensed.

## The real-data demo

We ran Patchline on Stripe's actual published OpenAPI specs (two release snapshots
from their public `stripe/openapi` repo, ~8MB each):

| | |
|---|---|
| Total changes detected | **679** |
| Breaking | **16** |
| Additive | 663 |

Including: **`card.iin` removed with no replacement field** — any code doing
`token.card.iin.slice(0, 6)` for BIN routing compiles fine and dies at runtime.

## Install

```bash
pip install -e .          # from this repo (Python 3.10+, zero dependencies)
```

## Quickstart

```bash
# 1. Diff two specs (writes a full JSON report)
patchline diff examples/pay_api_v1.json examples/pay_api_v2.json --out diff.json

# 2. Map the breaking changes to your code
patchline scan --repo examples/consumer --report diff.json
```

Output:

```
PayAPI: v1 (2025-03-01) -> v2 (2026-07-01.dahlia)
7 changes: 4 BREAKING, 3 additive

  [BREAKING] endpoint_removed         GET   /v1/charges/{id}  GET /v1/charges/{id} was removed
  [BREAKING] response_type_changed    POST  /v1/charges       Response field 'billing_details.address' changed type string -> object
  [BREAKING] enum_value_removed       POST  /v1/charges       Enum value 'pending' removed from 'status'
  [BREAKING] request_required_added   POST  /v1/refunds       New required request field 'reason' on POST /v1/refunds

4 breaking changes -> 7 affected call site(s) in examples/consumer
  billing.js:10    [response_type_changed] return charge.billing_details.address.split(",")[1].trim();
  billing.js:2     [endpoint_removed]      const CHARGE_URL = (id) => `/v1/charges/${id}`;
  ...
```

Exit codes double as a CI signal: `1` when breaking changes (or affected call sites)
are found, `0` when clean — drop it into your pipeline to catch dependency drift on
every build.

## What it detects

| Class | Severity | Example |
|---|---|---|
| Endpoint removed | BREAKING | `GET /v1/charges/{id}` gone |
| Response field removed | BREAKING | `card.iin` no longer returned |
| Response type changed | BREAKING | `address`: string → object |
| Enum value removed | BREAKING | `status: "pending"` retired |
| Required request field added | BREAKING | `reason` now mandatory |
| Endpoint / field added | additive | informational |

Real-world spec support: OpenAPI 3 `content` wrappers, local `$ref` resolution
(cycle- and depth-guarded), JSON and form-encoded request bodies.

## Open source vs. Patchline Cloud

This repo is the detection core: diff + classify + call-site scan.
The commercial product adds **remediation**: an agent that rewrites the affected
call sites and opens a pull request — gated on your own CI passing — plus a
continuous watcher for the APIs you depend on. Detection without remediation is
just a nicer alarm bell; the cloud product closes the loop.

## Contributing

Issues and PRs welcome — especially new change-class patterns and scanner heuristics
for other languages (the v1 scanner targets JS/TS call sites).

## License

MIT — see [LICENSE](LICENSE).
