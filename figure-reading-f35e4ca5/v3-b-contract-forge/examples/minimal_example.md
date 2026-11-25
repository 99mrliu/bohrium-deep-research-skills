# Minimal end-to-end example (合成示例 / synthetic — 所有输出均为示意输出)

Everything below is **synthetic**: the case, figure, table, and all outputs are
demonstration artifacts produced by `make_synthetic_case.py` (case_id
`synthetic-demo-B`). No real measurement data is involved.

## 0. Generate the synthetic case

```bash
python3 examples/make_synthetic_case.py --out /tmp/f35e-b-demo
# exit 0 -> /tmp/f35e-b-demo/{case.json, task.md, figure.png, table.csv}
```

## 1. Parse the contract — the skeleton IS the early partial result

```bash
python3 scripts/contract_parse.py \
  --case /tmp/f35e-b-demo/case.json \
  --task /tmp/f35e-b-demo/task.md \
  --work /tmp/f35e-b-demo/work \
  --out /tmp/f35e-b-demo/output
# exit 0
# {"case_id": "synthetic-demo-B", "degraded": false, "n_fields": 21, "n_required": 21, ...}
cp /tmp/f35e-b-demo/output/result_skeleton.json /tmp/f35e-b-demo/output/result.json
```

Skeleton excerpt (示意输出): contract shape with null leaves, honesty fields attached:

```json
{
  "figure": {"axes": {"x": {"type": null, "unit": null, "range": null}, "y": {...}},
             "series": [{"name": null, "unit": null, "data_points": [{"x": null, "y": null}]}]},
  "answers": [{"question": null, "answer": null, "evidence": null}],
  "statistics": {"n_comparisons": null, "alpha": null},
  "gaps": [],
  "case_id": "synthetic-demo-B",
  "status": "partial",
  "sources": [], "uncertainty": [], "change_records": []
}
```

## 2. (agent reads the figure) Fill ~half the fields via a fragment

Fragment `/tmp/f35e-b-fragment-partial.json` (示意输入) — note the `_source` locator map
and the deliberately over-claimed `"status": "success"`:

```json
{
  "_source": {
    "/figure/axes": "figure.png axis titles and tick labels",
    "/figure/series": "figure.png legend + plotted line; values cross-checked against table.csv",
    "/answers": "task.md Q1-Q3; figure.png"
  },
  "figure": {
    "axes": {
      "x": {"type": "linear", "unit": "s", "range": [0, 10]},
      "y": {"type": "linear", "unit": "nm", "range": [0, 100]}
    },
    "series": [{"name": "sample A", "unit": "nm",
                "data_points": [{"x": 0, "y": 0.0}, {"x": 2, "y": 43.5},
                                {"x": 5, "y": 76.0}, {"x": 8, "y": 89.8}, {"x": 10, "y": 94.3}]}]
  },
  "answers": [{"question": "What are the x and y axis quantities and their units?",
               "answer": "x: time in s; y: particle size in nm",
               "evidence": "figure.png axis titles"}],
  "status": "success"
}
```

```bash
python3 scripts/contract_fill.py \
  --skeleton /tmp/f35e-b-demo/output/result.json \
  --fragment /tmp/f35e-b-fragment-partial.json \
  --work /tmp/f35e-b-demo/work
# exit 0
# {"changed_leaves": 24, "fields_non_null": 24, "fields_total": 26, ...}
```

`work/change_log.jsonl` now holds exactly one record per changed leaf (24 lines),
e.g.:

```json
{"ts": "...", "path": "/figure/axes/x/unit", "old": null, "new": "s", "source": "figure.png axis titles and tick labels"}
```

## 3. Lint — auto-downgrade in action

```bash
python3 scripts/contract_lint.py \
  --case /tmp/f35e-b-demo/case.json \
  --result /tmp/f35e-b-demo/output/result.json \
  --plan /tmp/f35e-b-demo/work/contract_plan.json
# exit 2
```

`lint_report.json` excerpt (示意输出) — `statistics` was left null, so the claimed
`success` is mechanically downgraded and result.json is rewritten to `"partial"`:

```json
{
  "fatal": false,
  "downgraded": true,
  "n_violations": 3,
  "violations": [
    {"check": "coverage", "path": "/statistics/n_comparisons",
     "message": "required field is null (no documented reason)"},
    {"check": "coverage", "path": "/statistics/alpha",
     "message": "required field is null (no documented reason)"},
    {"check": "status", "path": "/status",
     "message": "auto-downgraded \"success\" -> \"partial\": 2 required field(s) null/missing"}
  ],
  "null_required_paths": ["/statistics/n_comparisons", "/statistics/alpha"],
  "final_status": "partial"
}
```

## 4. Fill everything, lint again — clean success

A second fragment fills `statistics`, the remaining two `answers`, `sources`, and sets
`"uncertainty": []`, `"gaps": []`, `"status": "success"`:

```bash
python3 scripts/contract_fill.py \
  --skeleton /tmp/f35e-b-demo/output/result.json \
  --fragment /tmp/f35e-b-fragment-full.json \
  --work /tmp/f35e-b-demo/work
# exit 0  {"changed_leaves": 12, "fields_non_null": 32, "fields_total": 32, ...}

python3 scripts/contract_lint.py \
  --case /tmp/f35e-b-demo/case.json \
  --result /tmp/f35e-b-demo/output/result.json \
  --plan /tmp/f35e-b-demo/work/contract_plan.json
# exit 0  {"fatal": false, "downgraded": false, "n_violations": 0, "final_status": "success"}
```

## 5. Fatal path — case_id tampering

```bash
# tamper a COPY of the result
python3 scripts/contract_lint.py \
  --case /tmp/f35e-b-demo/case.json \
  --result /tmp/f35e-b-demo/output/result_tampered.json \
  --plan /tmp/f35e-b-demo/work/contract_plan.json \
  --out /tmp/f35e-b-demo/output/lint_report_tampered.json
# exit 1  ->  "FATAL: result case_id 'tampered-id' does not match case.json case_id 'synthetic-demo-B'"
```

Fill-time protection likewise refuses `case_id` changes (exit 2, `"refused":
["/case_id"]`, value preserved).

## Deliverable set (what would be copied to /app/output)

`result.json` (final, status honest), `lint_report.json` (proof it was checked),
`work/change_log.jsonl` (proof of how it was built).
