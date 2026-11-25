# Scope field dictionary

The dictionary defines a record of one bounded scientific conclusion. It does not assign scientific validity.

| Field | Required content and scope rule |
|---|---|
| `record_id` | Unique local identifier. |
| `claim_id` | Identifier of the conclusion this record bounds. A conclusion may need several records for arms, strata, or endpoints. |
| `classification` | `demonstrated`, `inferred`, `not_reported`, or `conflicting`. Demonstrated means directly reported in the supplied evidence, not necessarily true or causal. |
| `subject_population_material` | Exact organism/population/material/model, including relevant subtype, geometry, eligibility, or batch. Do not broaden coupons to components, cells to patients, or one alloy to all alloys. |
| `intervention_method` | Exposure, treatment, algorithm, assay, or analytic method with dose/settings where relevant. |
| `comparator` | Actual control/comparator and its conditions. Use `NA` only when no comparator is scientifically applicable, with a reason. |
| `dataset_sample` | Dataset/cohort/sample identity, sample size, splits, selection, and source scope. Separate training, validation, and test sets. |
| `experimental_conditions` | Duration, environment, temperature, endpoint/time point, preprocessing, and other restrictions needed to reproduce the direction. |
| `metric_unit` | Endpoint name and exact unit/scale. Preserve direction conventions and uncertainty if supplied; this skill does not recompute values. |
| `direction_effect` | Reported direction and effect as stated, tied to comparator and stratum. Include null and opposite effects. No cross-unit conversion is implied. |
| `limitations` | Internal and external restrictions, conflicts, missing dimensions, and untested domains. `NR` requires searched locations. |
| `inference_reasoning` | Required for `inferred`; separates the author's or analyst's extrapolation from direct results. |
| `not_reported_basis` | Required for `not_reported`; identifies targeted sections/searches and what remains unknown. |
| `conflict_note` | Required for `conflicting`; identifies the incompatible evidence without silently choosing a winner. |
| `evidence` | Array of `{source, anchor, quote}`. The quote must occur verbatim inside the named anchored region of the supplied source. Demonstrated/inferred records need at least one; conflicting records need at least two. |

## Explicit missing values

Each of the eight scope dimensions must be either a nonempty string or exactly:

```json
{"status":"NR","reason":"Not reported in Methods, Results, Table 1, or Discussion."}
```

or:

```json
{"status":"NA","reason":"No comparator applies because this is a single-arm descriptive assay."}
```

`NR` is not `NA`; neither is an empty string, `null`, or an unsupported guess. An `NR` dimension can keep an otherwise useful record partial and must be surfaced in uncertainty.

## Evidence source behavior

`source` is a path relative to the explicit `--source-root`. Absolute paths and `..` escapes are rejected. The checker recognizes explicit plain-text anchors on separate lines such as `[S1]`; a quote is matched only within that anchor's region. Runtime PDF anchors may use page/section syntax, but automatic verification then requires converted text retaining the same anchor convention. A failed match can mean wrong quote, wrong region, damaged extraction, or an unreadable/missing source, and must be diagnosed accordingly.

## Claim-to-record links

For a nonuniversal claim, every ID in `scope_record_ids` must identify an existing record whose `claim_id` equals that claim's ID. An aggregate synthesis that deliberately incorporates a separately owned bounded premise must document the exception explicitly:

```json
"scope_record_link_exceptions": {
  "R-OTHER": {
    "kind": "composition",
    "reason": "The aggregate includes this bounded premise while retaining its original conclusion identity."
  }
}
```

The exception object contains exactly `kind` and a nonempty `reason`, and its record ID must also occur in `scope_record_ids`. It permits a cross-conclusion structural link only; it does not establish semantic consistency or support. Declared universal audits are intentional aggregates and may link the bounded records they adjudicate without per-record exceptions. The same exception mechanism cannot be used to declare an invalid schema check or an unclosed universal valid.

## Scope mesh structure

A useful mesh contains: bounded conclusion IDs; one or more scope records per conclusion; source evidence; relevant methods/results/tables/discussion closure entries; exception-search terms; counterexample links and dispositions; and a bounded restatement for every rejected universal. Keep a direct QA answer short when a full mesh adds no value. For scope/extrapolation work, every included scope/extrapolation note still needs all eight dimensions; ordinary QA uses only the records and dimensions needed to preserve its direct answer.
