# Check API changes in a pull request

This example compares a repository's `api/openapi.json` with the PR's base
commit, then scans `src`. Change those two paths for your project. It assumes
both revisions contain the spec and the document is JSON with local references.

Save this as `.github/workflows/api-compatibility.yml` in your own repository:

```yaml
name: API compatibility
on: pull_request
permissions:
  contents: read
jobs:
  compare:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install Patchline
        run: python -m pip install https://github.com/Xenrai/patchline/releases/download/v0.3.0/patchline-0.3.0-py3-none-any.whl
      - name: Compare API and locate potential callers
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
        shell: bash
        run: |
          mkdir -p .patchline
          git show "$BASE_SHA:api/openapi.json" > .patchline/before.json
          set +e
          patchline diff .patchline/before.json api/openapi.json --out .patchline/report.json
          diff_status=$?
          if [ "$diff_status" -gt 1 ]; then exit "$diff_status"; fi
          patchline scan --repo src --report .patchline/report.json --out .patchline/sites.json
          scan_status=$?
          if [ "$scan_status" -gt 1 ]; then exit "$scan_status"; fi
          exit "$diff_status"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: api-compatibility
          path: .patchline/*.json
```

The API diff determines the gate: `BREAKING` and `REVIEW` findings fail it even
when the heuristic scanner finds no callers. Exit `2` is an input or IO failure.
The source scan does not execute repository code. No API key is needed.

For a third-party API, store the approved spec snapshot in your repository and
compare it with the proposed snapshot. Fetching and choosing snapshots is outside
Patchline's scope; the tool itself compares local files without network calls.
