# Independent semantic checklist

Write the checklist from the task and actual sources **before** looking at the new artifact.
The expected matrix operationalizes this checklist; it must not be reverse-engineered from a
rendered SVG or the scene/IR that renders it.

## Required top-level record

```json
{
  "schema": "dual-artifact-quality-gate/semantic-checklist-v1",
  "case_id": "actual-case-id",
  "synthetic": false,
  "expectation_basis": ["task.md", "truth_table.json"],
  "gates": [
    {
      "id": "coverage",
      "required": true,
      "criterion": "Every required truth fact is consumed by at least one expectation.",
      "review_question": "Does the visible figure answer every requested source-bound item?",
      "evidence": ["truth_table.json", "expected_matrix.json", "visual_review.json"]
    }
  ],
  "source_review_requirements": {
    "figure03_primary_biological_source": {
      "required": false,
      "reason": "Not named by this case; absence was verified in the inventory."
    },
    "actual_chart_comparison": {
      "required": true,
      "reason": "The requested artifact contains actual charts."
    }
  }
}
```

Required gate IDs are exactly:

- `coverage`
- `source_support`
- `direction_marker_semantics`
- `numbering_order`
- `legend_style`
- `chart_data_values`
- `editable_layers`
- `export_validity`
- `result_contract`
- `source_preserving_edit_diff`

A gate that does not apply must be `required:false` with a concrete case-derived reason. Do
not use N/A to avoid a failed requirement. In particular, an existing-source edit cannot mark
`source_preserving_edit_diff` N/A, a chart case cannot mark `chart_data_values` N/A, and a case
requiring figure03 cannot waive `figure03_primary_biological_source`.

## Review semantics

| Gate | Agent/human must actually review | Scripts may check only |
|---|---|---|
| coverage | Requested entity, relation, annotation, data and output visible | Truth IDs referenced; observation paths exist |
| source_support | Label meaning and source terminology; no unsupported claim | Expected label equals observed label; evidence strings present |
| direction_marker_semantics | Arrowhead location and intended process/material/information direction | Observed endpoints and marker IDs equal expectations |
| numbering_order | Source sequence, parallel branches, recurrence and termination | Stored/visible order values and ordering constraints |
| legend_style | Visible legend mapping and redundant semantic cues | Fill/stroke/dash/text consistency |
| chart_data_values | Category/series/unit/sign/scale and actual source table comparison | Numeric/string consistency between SVG observation and CSV |
| editable_layers | Text and marks can be independently selected and changed | Named SVG groups, text count, stable IDs, chart marks |
| export_validity | Actual opening/rendering, dimensions, clipping, fonts, requested geometry | Signatures, XML parse, nonzero dimensions, file hashes |
| result_contract | Honest status, source/uncertainty/change disclosure | Required top-level keys and local path existence |
| source_preserving_edit_diff | Unaddressed appearance and structure remain intact | XML node/attribute allowlist diff and nonzero visual diff |

A checklist is not a set of renderer assertions. For example, `REACTOR` in the same scene
object used to render and inspect is one assertion checked twice. The required pattern is:

1. agent extracts `REACTOR` from source line/page;
2. agent writes an expected observation independently;
3. observer parses visible SVG text;
4. agent compares the actual rendered figure with the original source;
5. gate reports structural agreement plus a separate semantic review record.

## Figure03 and biological-source review

When required, the checklist must demand an original-source record containing:

- filename and publication/source identity, version/date and stable locator;
- original figure03 preview actually inspected, plus caption/methods as relevant;
- primary biological source actually inspected, not only secondary descriptions;
- explicit comparison of names, cardinalities, connections, markers/direction and numbering;
- unresolved source ambiguity and any intentional simplification.

Absence of these records blocks `success`. A cropped final figure is not the original
figure03. OCR/provided extraction is an aid, not the original visual evidence.

## Actual chart comparison

For every chart, the agent must inspect the actual chart and actual table/CSV. Expected values
come from cells with sheet/row/column locators. The observer independently parses the SVG marks
and CSV. The visual review additionally checks units, signs, series labels, category order,
axis scales and whether the visual encoding faithfully distinguishes values. Zero height,
truncated axes, log scales or missing baselines may require semantic review even if numbers
match. No check in this bundle proves chart correctness by itself.

## Changing expectations

If later source reading reveals an expectation error, preserve the original matrix and record
an expectation change with old value, new value, source locator, and rationale. Never change
an expectation solely to agree with the artifact. A source conflict remains an uncertainty
until genuinely resolved.
