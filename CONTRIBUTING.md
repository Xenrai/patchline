# Contributing to Patchline

Start with a small, reproducible API change or scanner example. A useful report
includes a minimal old/new JSON spec, expected classification, actual output,
and a short source snippet if call-site matching is involved.

## Run locally

```bash
git clone https://github.com/Xenrai/patchline.git
cd patchline
python -m pip install -e .
python -m unittest discover tests -v
patchline demo
```

Python 3.10+ is required. Runtime and unit tests use the standard library.

## Send a change

1. Fork the repository and create a branch for one specific improvement.
2. For behavior changes, add a regression showing a real failure or missed case.
3. Keep findings deterministic and preserve the `0` / `1` / `2` CLI exit contract.
4. Document new limits or classification changes. Unsupported schemas must not
   be presented as proven incompatibilities.
5. Run the suite and open a pull request describing the user-visible result.

CI tests Windows and Linux, builds a wheel, and runs its demo in an isolated
environment outside the checkout. The Stripe baseline should change only after
reviewing why the findings changed; do not update counts just to make CI pass.

## Useful first contributions

- Small scanner regressions for Python dictionary access or JavaScript optional chaining.
- Minimal paired specs for an unsupported OpenAPI shape, with expected behavior.
- Clearer error messages with a reproducer and a test.
- Documentation tested on a platform you use.

Discuss composition analysis, YAML support, and AST-based scanning in an issue
before a large implementation. These need a defined compatibility policy.

If you use Patchline, a short account of your API, language, and false positives
is valuable feedback. A star helps people find it; fork when you want to change it.
