# SYNTHETIC EXAMPLE — never official results

This file records actual local execution of the synthetic fixture on 2026-11-25.
It is not a benchmark, an official case result, or a claim of performance on real
papers. Commands below were run from the skill root with Python's standard
library and `PYTHONDONTWRITEBYTECODE=1`.

## End-to-end runner

Actual command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 examples/minimal/run_example.py
```

Observed process exit: **0**. The runner printed a JSON summary with these actual
subprocess exits:

```text
geometry_pass_exit = 0
curated_pass_exit = 0
failure_test_exit = 2
```

The exact commands recorded in the generated `output/test-summary.json` were:

```bash
python3 scripts/runtime.py --input-dir examples/minimal --work-dir examples/minimal/work --output-dir examples/minimal/output
python3 scripts/runtime.py --input-dir examples/minimal --work-dir examples/minimal/work --output-dir examples/minimal/output --bindings examples/minimal/curated-cell-bindings.json
python3 scripts/runtime.py --input-dir examples/minimal --work-dir examples/minimal/failure-work --output-dir examples/minimal/failure-output --bindings examples/minimal/failure-work/invalid-header-bindings.json
```

### Geometry-only pass observation

The first pass wrote `output/result.json` before reconstruction and finished with
`status=partial`. It reconstructed one logical table with two page segments. All
three fields remained `extraction_failed`, all three scalar values remained null,
and no field claims were emitted. This directly checked that cell candidates are
not treated as answers without a binding.

### Curated pass observation

The curated pass printed:

```json
{"status": "answered", "fields": 3, "reported": 2, "result": "examples/minimal/output/result.json"}
```

Inspection of the generated text JSON confirmed:

- exactly three unique field IDs in target order;
- statuses `reported`, `reported`, `not_reported`;
- scalar strings `42.0` and `51.3`, both with `%`; decimal trailing zero and units
  were not normalized or converted;
- page-1 paragraph/cell `s001-seg001-r02-c03`, full-cell quote `42.0`;
- page-2 paragraph/cell `s001-seg002-r02-c03`, full-cell quote `51.3`;
- both `experimental_condition` and `condition` retained catalyst, temperature,
  and `at 24 h` identically;
- catalyst C preserved two yield-header cells in its value location, namely the
  inherited page-1 header and repeated page-2 continued header;
- catalyst C also carried exact condition-cell evidence for `C`, `80`, original
  and continued temperature headers, and original and continued `24 h` headers;
- selectivity had null scalar and empty value evidence, retained its scoped
  `Catalyst=C; Temp=80 °C; at 24 h` condition, and its notes named all six
  reviewed header/data rows, thereby distinguishing absence from extraction failure;
- task input stayed separate from scientific evidence, and sources included the
  actual fixture SHA-256 and input-relative path.

The generated `output/table-preview.md` contained 38 lines and the visible
three-column page-2 table. Its effective paths were:

```text
Column 1: s001-seg001-r01-c01, s001-seg002-r01-c01
Column 2: s001-seg001-r01-c02, s001-seg002-r01-c02
Column 3: s001-seg001-r01-c03, s001-seg002-r01-c03
```

The generated `output/table-preview.svg` was inspected as UTF-8 SVG text and in a
real headless-Chrome `1200 × 353` viewport on 2026-11-25. All three columns,
both page segments, continued headers, values, and stable cell IDs were visible
without clipping; the synthetic label was prominent. It had `<text>` nodes for
all values and stable cell IDs, including `51.3` and
`Yield (%) at 24 h (continued)`, and parsed successfully as XML. The browser was
used only for inspection and is not a runtime dependency. The full quote
fallback in `work/tables.json` remained available for text longer than the SVG's
visible 44-character preview limit. The reported cells had null `statistic`;
the metric name `Yield` was not mislabeled as a statistical measure.

## Independent contract and SVG validation

Actual command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_result.py --result examples/minimal/output/result.json --target-fields examples/minimal/target-fields.json --svg examples/minimal/output/table-preview.svg
```

Observed exit: **0**, with actual stdout:

```json
{"valid": true, "case_id": "SYNTHETIC-EXAMPLE-NOT-OFFICIAL", "status": "answered", "field_count": 3, "field_ids": ["yield_A_25C_24h", "yield_C_80C_24h", "selectivity_C_80C_24h"], "svg_text_nodes": 47}
```

## Deliberate meaningful failure test

The runner loaded the valid curated binding, kept the correct value-cell ID and
scalar unchanged, but deliberately replaced exact expected header
`Yield (%) at 24 h` with the condition-losing `Yield (%)`. It used separate
failure work/output directories so the successful synthetic result was not
mistaken for the rejected run.

Observed exit was **2**, not silent acceptance. `output/failure-observation.txt`
contains the actual observed error:

```text
Reviewed bindings rejected; no candidate answer was promoted: Binding for yield_A_25C_24h: column header text differs: Yield (%) at 24 h != Yield (%)
```

Inspection of `failure-output/result.json` confirmed all three fields remained
`extraction_failed` with null scalar and empty evidence, overall status remained
`partial`, and a `binding_rejected` uncertainty was present. Thus the negative
case tested semantic/condition retention, not mere JSON syntax or a missing file.

## Reproduction notes

The runner replaces only the four generated directories under this synthetic
example: `work`, `output`, `failure-work`, and `failure-output`. Every generated
JSON/Markdown/SVG/TXT artifact carries the synthetic label through the case or its
inspection header. Real evaluation inputs are not included here.
