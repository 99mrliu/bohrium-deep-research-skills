# Evidence schemas

All files are UTF-8 JSON unless noted. Use stable IDs and relative paths inside a report so
runs in different output directories are comparable. `synthetic:true` is mandatory for the
invented demonstration and forbidden as a label for real case inputs.

## 1. Extraction truth table (agent-derived)

```json
{
  "schema": "dual-artifact-quality-gate/truth-table-v1",
  "case_id": "actual-case-id",
  "synthetic": false,
  "derived_by": "agent from actual sources",
  "facts": [
    {
      "truth_id": "entity.reactor.label",
      "kind": "entity",
      "subject": "reactor",
      "predicate": "label",
      "value": "REACTOR",
      "required": true,
      "source": {
        "path": "sources/method.md",
        "locator": "line 3",
        "quote": "FEED enters the PUMP and then the REACTOR."
      }
    },
    {
      "truth_id": "chart.measurement.run_b",
      "kind": "chart_value",
      "subject": "Measurement|Run B",
      "predicate": "value",
      "value": 4.0,
      "required": true,
      "source": {
        "path": "sources/measurements.csv",
        "locator": "row 3, columns series/category/value",
        "quote": "Measurement,Run B,4.0,units"
      }
    }
  ],
  "extraction_uncertainties": []
}
```

Do not populate this table from a scene or SVG. Table facts may use exact cell references and
a verbatim row instead of prose. For figures, include source page/figure/panel and an actual
visual observation; wording alone cannot locate an arrowhead.

## 2. Expected observation matrix (agent-derived before artifact)

```json
{
  "schema": "dual-artifact-quality-gate/expected-matrix-v1",
  "case_id": "actual-case-id",
  "synthetic": false,
  "basis": ["task.md", "truth_table.json", "semantic_checklist.json"],
  "expectations": [
    {
      "check_id": "source.reactor.label",
      "gate": "source_support",
      "truth_ids": ["entity.reactor.label"],
      "path": "svg.entities.reactor.label",
      "op": "eq",
      "expected": "REACTOR",
      "severity": "error"
    },
    {
      "check_id": "chart.svg.run_b",
      "gate": "chart_data_values",
      "truth_ids": ["chart.measurement.run_b"],
      "path": "svg.chart_values.Measurement|Run B.value",
      "op": "approx",
      "expected": 4.0,
      "tolerance": 1e-9,
      "severity": "error"
    },
    {
      "check_id": "chart.csv.run_b",
      "gate": "chart_data_values",
      "truth_ids": ["chart.measurement.run_b"],
      "path": "csv.measurements.csv.values.Measurement|Run B.value",
      "op": "approx",
      "expected": 4.0,
      "severity": "error"
    },
    {
      "check_id": "layers.required",
      "gate": "editable_layers",
      "truth_ids": [],
      "path": "svg.layer_set",
      "op": "includes_all",
      "expected": ["entities", "flows", "chart"],
      "severity": "error"
    }
  ]
}
```

`check_id` values must be unique. `gate` must be a checklist gate. Every required truth fact
must be named by at least one expectation. Expectations can have no truth ID only for delivery
properties taken directly from the task, in which case add `task_basis` with a locator.
Severity is `error` or `warning`; required gates must not consist only of warnings.

Supported operators are documented in `observation-contract.md`. Matrix comparisons are
structural consistency checks, not proof that expected values are scientifically correct.

## 3. Rendered observations

Produced solely by `artifact_observer.py --svg figure.svg [--csv actual.csv ...]`. Do not
manually repair this file. If the parser is wrong, retain the original and record the parser
limitation; rerun on a compliant visible artifact. See `observation-contract.md`.

## 4. Visual review and visual diff

See `review-and-repair.md`. Each covered gate has a separate agent/human `gate_reviews` item.
Required figure03/primary biological source and chart comparisons are explicit records.
`visual_diff.json` from `png_diff.py` stores actual image paths, dimensions, hashes, pixel
metrics, review record hashes, and any errors. Pixel change is evidence of difference only.

## 5. Source edit diff and intent

See `review-and-repair.md`. `source_edit_diff.json` identifies changed IDs, attributes, text,
unchanged required IDs, unauthorized changes, and before/after hashes. New figures use an
explicit checklist N/A; existing-source edits require this report.

## 6. Export audit

`export_audit.json` contains one entry per requested existing export, with file path, SHA-256,
byte count and parsed structural facts. SVG must be parseable XML; PNG must have valid
signature/IHDR and nonzero dimensions; PDF must have a header and EOF marker. These checks do
not prove visual fidelity or fonts. `errors` is empty for supplied valid files. An omitted
required export must be separately disclosed and fails contract/completeness review.

## 7. QC report and residual defects

`semantic_gate.py` writes a report even on failure:

```json
{
  "schema": "dual-artifact-quality-gate/qc-report-v1",
  "case_id": "actual-case-id",
  "scientific_correctness": "not established by this structural/consistency report",
  "status": "pass",
  "checks": [
    {"check_id": "source.reactor.label", "gate": "source_support",
     "status": "pass", "expected": "REACTOR", "observed": "REACTOR",
     "code": "PASS"}
  ],
  "gate_summaries": {"coverage": {"status": "pass"}},
  "evidence_audits": {
    "visual_review": {"status": "pass"},
    "export_validity": {"status": "pass"},
    "result_contract": {"status": "pass"}
  },
  "residual_errors": [],
  "warnings": [],
  "parser_limitations": []
}
```

Mismatch codes include `LABEL_MISMATCH`, `DIRECTION_MISMATCH`, `MARKER_MISMATCH`,
`ORDER_MISMATCH`, `LEGEND_STYLE_MISMATCH`, `CHART_VALUE_MISMATCH`, `MISSING_OBSERVATION`,
`COVERAGE_GAP`, `VISUAL_REVIEW_FAIL`, `EXPORT_INVALID`, `CONTRACT_INVALID`, and
`SOURCE_PRESERVATION_FAIL`. A mismatch code is based on gate/path semantics and is diagnostic,
not a scientific classifier. Any residual error makes the command nonzero.

## 8. Result and contract audit

The case's `output_contract` keys are copied verbatim to **top level**. `case_id`, `status`,
`sources`, `uncertainties`, and `change_records` are also top level:

```json
{
  "case_id": "actual-case-id",
  "editable_svg": "figure.svg",
  "preview_png": "figure.png",
  "semantic_checklist": "semantic_checklist.json",
  "expected_matrix": "expected_matrix.json",
  "rendered_observations": "rendered_observations.json",
  "visual_review": "visual_review.json",
  "visual_diff": "visual_diff.json",
  "source_edit_diff": "source_edit_diff.json",
  "export_audit": "export_audit.json",
  "contract_audit": "contract_audit.json",
  "qc_report": "qc_report.json",
  "status": "success",
  "sources": [
    {"path": "sources/method.md", "locator": "lines 1-4", "used_for": "labels and flow"}
  ],
  "uncertainties": [],
  "change_records": [
    {"target": "reactor-label", "before": "VESSEL", "after": "REACTOR",
     "truth_ids": ["entity.reactor.label"], "reason": "Source-backed label correction"}
  ]
}
```

Contract values may be relative to `/app/output` or absolute paths inside it. Missing/null
paths are accepted only in an early `partial`/`failed` checkpoint and remain errors for a
claimed complete success. The final status is `success`, `partial`, or `failed`; no `ok`.
All final artifacts/reports must be under `/app/output`. Contract audit checks field placement
and path existence; the agent remains responsible for honest status and disclosures.
