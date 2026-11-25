# Synthetic examples

All content under `synthetic/` is invented test material. It is not derived from actual papers, hidden inputs, platform data, C01/C02/C03, or prepared challenge answers.

From the bundle root, run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_synthetic_example.py
```

The runner resets only its own example `work/` and `output/` directories, then tests:

1. **Normal end-to-end** — two MathML occurrences, including a nested fraction, `msubsup`, `velocity` as one `mi`, an explicit fenced matrix, and a cube root. It generates `synthetic/work/mathml/catalog.{json,md}`, individual IR/LaTeX/roundtrip files, `roundtrip-verification.json`, and the real dynamic-contract `synthetic/output/result.json`. Both roundtrips must pass. The authored result remains `partial` because the invented source supplies no derivation.
2. **Expected unknown-tag failure** — `synthetic/expected_failure/input/publisher-source.xml` contains the invented unsupported `mystery` tag and contradictory `alttext`. Extraction and strict verification must both exit `2`; `failure-test.json` records the assertions. The roundtrip can be structurally equal, but status stays `unsupported`, LaTeX carries an explicit marker, and publisher text stays a non-authoritative mismatch.
3. **No formula** — a disposable source under the example directory contains no `<math>`. Extraction and result assembly must emit `insufficient_evidence` and empty scientific claims, with valid contract field types.

The persistent machine-readable summary is `synthetic/test-results.json` after a successful run.
