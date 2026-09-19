# Changelog

## 0.3.0

- Add `patchline demo`, an offline example bundled in the installed wheel.
- Add `patchline --version`, package links, and installation verification outside
  the source checkout on all four CI configurations.
- Fix false field-removal findings when an object becomes a composed schema.
  Composition changes now use `REVIEW`, not `BREAKING`; diff still exits `1`
  so CI does not silently approve an unverified compatibility change.
- Reproduce the pinned Stripe comparison as 6,385 findings: four breaking
  field removals, one composition change requiring review, and 6,380 additive.
  Earlier reports incorrectly described the terminal-reader union as removed fields.
- Add a CI integration recipe, issue templates, and contribution instructions.

Reports now accept severity `REVIEW` and summaries include a `review` count.
Consumers that enumerate severity values must handle this additional value.

## 0.2.0

- Expand comparison to all response statuses, media representations, array
  items, required request bodies/parameters, and removed request media types.
- Add Python and JavaScript-module scanning, dependency-folder exclusions,
  deterministic results, and input error exit code `2`.
- Add Windows/Linux CI and 46 regression tests.

## 0.1.0

- Initial JSON API diff, JS/TS source scanning, and Stripe example.
