# Visual review, edit diff, and repair

## Genuine visual review

A real case must include an agent or human review of the actual rendered output. The observer
and gate do not synthesize this record. At minimum record:

```json
{
  "schema": "dual-artifact-quality-gate/visual-review-v1",
  "case_id": "actual-case-id",
  "round": 1,
  "reviewer": {"type": "agent", "identity": "actual executing agent"},
  "images_inspected": ["figure.png"],
  "source_comparisons": [
    {
      "source": "original.pdf",
      "locator": "figure03, page 7, and caption lines 4-9",
      "inspected": true,
      "observations": ["Original and rendered labels/connectors compared explicitly."]
    }
  ],
  "gate_reviews": [
    {"gate": "coverage", "status": "pass", "observations": ["..."], "defects": []}
  ],
  "chart_comparisons": [
    {"chart": "figure.svg#Measurements", "source": "actual.csv",
     "rows_compared": ["Measurement|Run A"], "status": "pass",
     "observations": ["Values, series, units and order visually compared."]}
  ],
  "residual_defects": []
}
```

Use `fail` for a visual/source mismatch and `pending` if the required review has not happened.
A gate review with `pass` requires concrete observations. `not_applicable` needs a reason.
The gate enforces record structure and failures, but cannot verify that the reviewer truly
looked; that responsibility remains with the executing agent.

For a required original figure03/primary biological source, list both original figure and
primary source under `source_comparisons`, with precise locators and explicit observations.
For actual charts, compare each series/category/value/unit/order against the real data. A CSV
parser match alone is not visual review.

## Before/after visual diff

`png_diff.py` compares decoded non-interlaced PNG RGB/RGBA/gray images of equal dimensions,
writes an actual diff PNG and reports differing pixel count, ratio, bounding box and hashes.
Different dimensions are reported as an error unless the intended resize is explicitly
reviewed; they are not normalized away. For unsupported PNG encodings, use another actual
image tool and record its command/results, or declare the limitation.

A pixel diff establishes that pixels changed. It does **not** establish that the new image is
better. Link resolved defects from before review to after review and source truth IDs. If no
pixels differ, an edit-improvement claim fails. If unrelated pixels changed, explain them and
check source-preservation. Preserve before and after images and reports in output.

## Source-preserving XML edit diff

`edit_intent.json`:

```json
{
  "schema": "dual-artifact-quality-gate/edit-intent-v1",
  "mode": "edit",
  "allowed_changes": [
    {"id": "reactor-label", "attributes": ["text"]},
    {"id": "flow-1", "attributes": ["d", "marker-end", "data-from", "data-to"]},
    {"id": "bar-run-b", "attributes": ["height", "y", "data-value"]}
  ],
  "required_preserve_ids": ["title", "pump", "legend", "unrelated-note"],
  "reason": "Correct only source-backed defects; all other structure is unaddressed."
}
```

The diff identifies elements by their XML `id` or `data-qc-id`. `text` permits textual content
change; `children` permits child-list changes; `attributes` lists allowed attribute changes.
Only listed IDs/attributes are allowed to change. Adding or removing IDs is an error unless an
entry has `"add":true` or `"remove":true`. An ID in `required_preserve_ids` must remain and
cannot be an allowed change target. Elements without IDs are compared by document position;
wholesale positional churn therefore fails rather than being mistaken for preservation.

Namespace/prefix formatting may need normalization before diffing. Use the original SVG as the
edit base. Do not flatten groups, convert text to paths, or reassign unrelated IDs. Keep the
report even when it fails.

## Repair rounds and residual defects

The initial artifact is round 1. At most two repairs (rounds 2 and 3) are allowed. After each:

1. retain the failed report and independent observation;
2. make only source-supported changes;
3. rerun the observer and export check;
4. repeat actual visual/source review and before/after diff for edits;
5. rerun result-contract audit and semantic gate;
6. copy every final report to `/app/output`.

An error in a final required gate means nonzero and prevents `success`. If the time or repair
budget ends, `status:"partial"` is honest only if the residual is explicit. Each residual
entry includes:

```json
{"code": "CHART_VALUE_MISMATCH", "gate": "chart_data_values",
 "status": "residual_error", "evidence": ["qc_report.json#checks[...]"],
 "impact": "Run B remains unsupported; do not use this chart quantitatively.",
 "attempted_repairs": 2}
```

Do not mark residual errors `resolved` without later passing evidence. Warnings must not hide
required errors. Missing source, ambiguous source, unavailable exporter, and unreviewed render
are different limitations and should be named separately.

## Determinism and negative verification

Run the synthetic negative fixture without modifying the checker. It must produce nonzero
and identify independent SVG-vs-source expectation mismatches for label, direction, and chart
value. Then the corrected fixture must pass with a nonempty source edit diff and visual pixel
diff. The fixture's names and values are invented and have no scientific meaning.
