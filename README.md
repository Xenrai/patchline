# Patchline

**An API changed. Which lines in your code should you review?**

Patchline compares two OpenAPI JSON specs, flags supported breaking changes,
and points to potential callers in JavaScript, TypeScript, and Python.

[![Tests](https://github.com/Xenrai/patchline/actions/workflows/test.yml/badge.svg)](https://github.com/Xenrai/patchline/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/Xenrai/patchline)](https://github.com/Xenrai/patchline/releases/latest)
[![MIT license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Python 3.10+ · zero runtime dependencies · offline analysis · no API keys

## Try it in a minute

Install the versioned wheel, preferably in your Python virtual environment:

```bash
python -m pip install https://github.com/Xenrai/patchline/releases/download/v0.3.0/patchline-0.3.0-py3-none-any.whl
python -m patchline demo
```

No checkout, API credentials, or sample downloads are needed after installation.
The demo runs the real differ and scanner on bundled OpenAPI 3 examples:

```text
4 breaking changes -> 4 potential call sites

  billing.js:2 [endpoint_removed] const CHARGE_URL = (id) => `/v1/charges/${id}`;
  billing.js:9 [enum_value_removed] return charge.status === "pending";
  billing.js:13 [response_type_changed] return charge.billing_details.address.split(",")[1].trim();
  refunds.js:3 [request_required_added] return client.post("/v1/refunds", { charge: chargeId, amount });
```

This is a review aid: source matches are heuristic, not proof that a caller breaks.
The demo exits `0` on completion and does not change your project files.

## Use your own API

```bash
patchline diff before.json after.json --out report.json
patchline scan --repo ./src --report report.json --out sites.json
patchline --version
```

Use `python -m patchline` if your environment does not put the command on PATH.

| Command result | Exit code |
| --- | --- |
| No supported findings | `0` |
| Diff has `BREAKING` or `REVIEW` findings; scan has potential call sites | `1` |
| Invalid input, unsupported reference, missing folder, or IO error | `2` |

**[Add the copyable GitHub Actions check](docs/ci.md)** to compare specs on pull
requests and save JSON reports. Gate CI on the diff: a scan with no matches
does not establish compatibility.

## What it catches

| Change | Classification |
| --- | --- |
| Endpoint or response representation removed | `BREAKING` |
| Response field removed; root, field, or array-item type changed | `BREAKING` |
| Response enum value removed | `BREAKING` (conservative policy) |
| Required top-level request field, parameter, or body added | `BREAKING` |
| Request media type removed | `BREAKING` |
| Schema composition changes (`anyOf`, `oneOf`, `allOf`) | `REVIEW` |
| Endpoint, response, or response field added | `ADDITIVE` |

The differ handles all eight OpenAPI HTTP methods, response statuses and media
representations, local references with escaped JSON Pointer tokens, arrays,
nullable types, and inherited parameters with operation-level overrides.
Report order is deterministic.

The scanner supports `.js`, `.ts`, `.jsx`, `.tsx`, `.mjs`, `.cjs`, and `.py`.
It skips dependency, build, cache, and Git directories and symlinks. It reads
UTF-8 source and never executes it.

## A reproducible Stripe example

The repository includes a report comparing Stripe's published OpenAPI tags
`v2250` and `v2349`. With v0.3.0:

| Findings | Count |
| --- | ---: |
| Breaking field removals | 4 |
| Schema changes requiring review | 1 |
| Additive findings | 6,380 |

The removals concern `iin` on card/token responses, including `data[].iin` in
a card-list response. The terminal-reader cancel-action response becomes an
`anyOf` union and requires review; Patchline does **not** claim its fields were
all removed. This corrects an overstatement in earlier reports.

These are contract findings, not a count of independent production failures.
[Read the generated report](examples/stripe/stripe-diff-report.json) or reproduce
it from a checkout:

```bash
python examples/stripe/run_stripe_diff.py
```

That separate example downloads the two pinned specs. Normal `diff`, `scan`,
and `demo` analysis runs offline. [Source snapshots](https://github.com/stripe/openapi).

## Know the limits

- Source matching is pattern-based: false positives and missed callers are possible.
- Schema traversal is capped at five levels. Composition changes are flagged
  for review; branch semantics and changes hidden behind unchanged composition
  references are not analyzed. JSON Schema constraint compatibility is incomplete.
- Request analysis does not compare nested requirements, parameter types,
  authentication, or validation bounds.
- Input is JSON with local references. YAML, external references, callbacks,
  and webhooks are unsupported. Input checks are not a full OpenAPI validator.
- Response enum removals are conservatively breaking; enum additions are not
  reported. Type changes are conservatively breaking.

If you need a complete compatibility proof, this tool does not provide one.

## Build on it

Found a missed API change or false positive? [Open a minimal example](https://github.com/Xenrai/patchline/issues/new/choose).
Want to improve it? [Read the contribution guide](CONTRIBUTING.md), fork the
repository, and add a focused regression. Useful contributions include scanner
examples, spec fixtures, and clearer errors.

```bash
git clone https://github.com/Xenrai/patchline.git
cd patchline
python -m pip install -e .
python -m unittest discover tests -v
```

CI covers Python 3.10 and 3.12 on Windows and Linux, including wheel installation
and the demo outside the checkout. [Changelog](CHANGELOG.md) · [MIT license](LICENSE).
