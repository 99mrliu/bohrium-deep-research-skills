# Numerical ledger schema (operational, version 1.0)

The executable ledger is JSON with this shape. The script performs strict semantic checks; this document defines the required anchors and provenance rather than merely validating a schema.

```text
{
  schema_version: "1.0" (optional),
  ledger_id: nonempty string,
  synthetic: boolean (optional; true requires synthetic labels),
  numbers_matter: boolean (optional; controls visual generation),
  sources: [{
    source_id: unique string,
    path: UTF-8 text path, absolute or relative to the ledger,
    uncertainty: string (optional)
  }],
  values: [{
    value_id: unique string,
    number: plain decimal string OR null only for not_reported or missing,
    unit: nonempty string,
    provenance: author_reported | independently_calculated |
                reader_inference | not_reported | missing,
    anchor: {
      source_id: declared source ID,
      locator: original page/section/table/figure identifier,
      row: original row identifier or explicit body condition,
      column: original column/measurement identifier,
      condition: experimental condition,
      unit: exactly the value unit,
      quote: short exact UTF-8 source substring, maximum 240 characters;
             omitted/null only for not_reported or missing,
      char_start: zero-based inclusive Python Unicode code-point offset (paired with char_end),
      char_end: exclusive offset; source_text[char_start:char_end] must equal quote exactly;
                omit both only for legacy/unreviewed anchors or not_reported/missing values
    },
    note: string (optional)
  }],
  calculations: [{
    calculation_id: unique string,
    operation: percent_relative_change | percentage_point_difference |
               ratio | difference | product | sum | division,
    provenance: independently_calculated,
    direction: signed | reduction,
    operands: {initial: value_id, final: value_id} for changes/ratios,
              {numerator: value_id, denominator: value_id} for division,
              or arbitrary named value_id roles for product/sum,
    ratio_order: final_over_initial | initial_over_final (ratio only),
    output_unit: explicit unit for division/product where needed,
    expected: independent decimal expectation as a string,
    expected_basis: string describing independent hand/source check,
    tolerance: {type: absolute | relative, value: decimal string},
    rounding: {places: integer 0..12,
               mode: ROUND_HALF_UP | ROUND_HALF_EVEN | ROUND_DOWN | ROUND_UP},
    note: string (optional)
  }],
  reconciliations: [{
    reconciliation_id: string,
    value_ids: at least two declared value IDs,
    status: consistent | conflict | not_checked | unreadable,
    note: condition/unit alignment and exact conflict explanation
  }],
  inferences: [{
    inference_id: string,
    statement: string,
    provenance: reader_inference,
    depends_on: calculation/value IDs,
    caveat: string
  }],
  uncertainties: [strings],
  limitations: [strings],
  visual_comparison: {
    enabled: boolean,
    derived_output: simple filename ending .svg,
    axis_label: optional nonempty label (maximum 80 characters) that must mention the common unit,
    original_render: platform-rendered original page path OR null (null produces missing status),
    original_crop: platform-rendered original crop path OR null,
    original_review: {
      status: consistent | conflict | partial | unreadable | not_reported | missing,
      checked_values: [strings],
      note: string
    },
    series: [{
      label: condition/method label,
      bars: [{label: control/treatment label, value_id: declared numeric value}]
    }]
  }
}
```

## Extraction rules

- One value ID represents one numerical appearance. Body and table repetitions receive separate IDs and are reconciled; they are not silently deduplicated.
- `independently_calculated` belongs to a calculation result. `reader_inference` is an interpretation or pixel estimate, with dependencies. Both `not_reported` and `missing` must have `number: null`; neither means zero. Use `not_reported` when a supplied source omits the value and `missing` when the required source/input itself was not supplied.
- For numerical values, the engine checks `quote` only at `char_start:char_end`, never via global source containment. Offsets use Python string (Unicode code-point) indexing. A wrong/incomplete/out-of-range region yields `region_not_matched` or `invalid_region`. A legacy anchor without offsets yields `locator_not_checked`; all three make dependent calculations `anchor_failed` and prevent an unqualified complete/pass status.
- A relative percent input often has unit `percent`; percentage-point output must have unit `percentage_points`. A ratio is normally `dimensionless`.
- The expected value must be justified independently of the engine. A failed comparison remains a mismatch and includes actual, expected, discrepancy, and tolerance.
- All operands inherit their source anchors and quote checks in the output. Formula strings are descriptive evidence, not executable expressions.
- Conflicts and unreadable/missing sources affect verification status. They are not removed to obtain a clean pass.
