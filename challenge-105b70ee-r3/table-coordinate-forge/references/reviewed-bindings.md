# Reviewed cell-binding schema

## Purpose

A binding is the agent's auditable semantic decision. It connects one requested
`field_id` to reconstructed cells after human/agent review of the original PDF.
The runtime checks the decision mechanically; it does not decide the science.
Copy `/app/work/reviewed-bindings.template.json` to
`/app/work/reviewed-bindings.json` and replace the template values.

Top level:

```json
{
  "schema_version": "table-coordinate-forge/reviewed-bindings-v1",
  "label": "case-specific review label",
  "bindings": []
}
```

There may be at most one binding per requested field. Unknown target IDs,
duplicate IDs, and unknown field statuses are rejected. Omitted fields remain
`extraction_failed`, enabling a valid partial result.

## 1. `reported`

Every reported binding contains all of these keys, even when a nullable semantic
field is null:

| Key | Requirement |
|---|---|
| `field_id` | Exact ID from `target-fields.json`; target order is restored in output. |
| `status` | `reported`. |
| `source_id` | Source generated in `result.sources`; must match cell source. |
| `cell_id` | Nonblank reconstructed value-cell ID. |
| `scalar` | Non-empty literal substring of the complete value-cell text. Keep as a string. |
| `units` | Verbatim unit substring in value/reviewed header context, or null. |
| `statistic` | Reviewed statistical statement (for example mean, SD, n, p, or CI), or null. Never substitute the metric name such as `Yield`. |
| `experimental_condition` | Complete reviewed condition string, or null only if genuinely inapplicable. |
| `comparator` | Verbatim/reviewed baseline or comparison, or null. |
| `row_header_cell_ids` | Other nonblank cells in the **same value row** used as row keys/conditions. |
| `column_header_cell_ids` | Non-empty ordered list of inherited/current effective headers for the value column. |
| `expected_row_header_text` | Exact full text for every row-header ID, in the same order. |
| `expected_column_header_text` | Exact full text for every column-header ID, in the same order. |
| `condition_cell_ids` | Additional cells in the same logical table proving all needed conditions. |
| `expected_condition_text` | Exact full text corresponding one-for-one with `condition_cell_ids`. |
| `notes` | Decision rationale, conditions checked, and any review caveat. |

The cardinal shape is:

```json
{
  "field_id": "requested-field",
  "status": "reported",
  "source_id": "source-001",
  "cell_id": "s001-seg001-r02-c03",
  "scalar": "VERBATIM SUBSTRING OF VALUE CELL",
  "units": "%",
  "statistic": "VERBATIM OR REVIEWED STATISTICAL STATEMENT, OR null",
  "experimental_condition": "ALL CONDITIONS PRESERVED",
  "comparator": null,
  "row_header_cell_ids": ["s001-seg001-r02-c01"],
  "column_header_cell_ids": ["s001-seg001-r01-c03"],
  "expected_row_header_text": ["EXACT ROW HEADER TEXT"],
  "expected_column_header_text": ["EXACT COLUMN HEADER TEXT"],
  "condition_cell_ids": ["s001-seg001-r01-c02"],
  "expected_condition_text": ["EXACT CONDITION HEADER"],
  "notes": "Explain the semantic review; a lexical match is not sufficient."
}
```

The `%` above illustrates that a unit is copied verbatim, not that percent is
assumed. Replace all placeholder strings with actual reviewed content. Empty row
header and condition arrays are permitted only where no further condition cells
are needed; column headers are mandatory for this table-specific binding route.

### Mechanical checks before acceptance

- Every ID exists in freshly reconstructed geometry; stale IDs from another layout
  are rejected.
- Value source matches the binding source and the scalar is a literal substring.
- A blank cell cannot supply a scalar. Nonblank placeholders or stale values are
  not invented.
- Row headers are different cells in the same row and their full texts exactly
  equal the expected-text array.
- Column headers belong to a reconstructed effective header path, overlap the
  value's column range, and exactly equal expected text. For continuation,
  include both inherited prior-page and repeated current-page IDs as needed.
- Condition cells belong to the same table and source and exactly match every
  supplied expected text. Their source/page/cell quotes are nested under the
  primary evidence as `condition_evidence`.
- Units are not inferred from the field name. They must be literal substrings of
  the value or reviewed header cells.

This redundancy is deliberate: changing or dropping `at 24 h`, a unit, or a
continued header in the expected text causes rejection rather than silent
condition loss.

### Scalar and quote distinction

`quote` in final output is the whole value-cell text. `scalar` can be a literal
part of that cell when the cell includes a unit or error notation. Never calculate
a new number. Examples of allowed behavior (not scientific answers):

- Cell `12.00 ± 0.20 mg`: scalar can remain `12.00 ± 0.20`, units `mg`, quote the
  entire cell if the requested quantity includes the uncertainty.
- Cell `0.10–0.20`: preserve the en dash and both decimal strings; do not average.
- Cell `45 %`: scalar `45`, units `%`, quote `45 %`, with the space still in quote.
- Cell `ND`, `—`, or blank: do not coerce to zero. Decide from the target and table
  semantics whether this is a verbatim reported token or a nonnumeric non-report;
  the current generic reported route requires a nonblank literal scalar.

`condition` is emitted as an exact alias of `experimental_condition`. `paragraph_id`
and primary `quote` equal the value cell's paragraph ID and full text. Evidence
also includes table, row, columns, header IDs, full cell page, and condition-cell
quotes.

## 2. `not_reported`

Use this only when a complete, scope-appropriate review establishes absence:

```json
{
  "field_id": "requested-field",
  "status": "not_reported",
  "experimental_condition": "CONDITION SCOPE, OR null IF INAPPLICABLE",
  "statistic": null,
  "comparator": null,
  "reviewed_scope": "Name every reviewed page, table segment, header hierarchy and note region relevant to the requested field.",
  "notes": "State what meanings were checked and why the source did not report the field; absence is not zero."
}
```

Scope and notes strings are required. Optional condition and comparator strings
preserve what absence was checked for; `condition` mirrors any supplied
experimental condition. Final scalar, units, statistic, and quote are null and no
value evidence is attached. Do not use `not_reported` when a parser failed, a PDF was unreadable,
a table candidate may have been omitted, a complex header was not understood, or
an out-of-scope source remains unreviewed. Those are `extraction_failed`.

## 3. `source_conflict`

Use when two or more cells support incompatible exact readings for the same field,
and neither can be discarded by the task's stated scope. Do not average, choose
the prettier value, or silently prefer a later page.

```json
{
  "field_id": "requested-field",
  "status": "source_conflict",
  "notes": "Explain why both reviewed candidate paths apply and remain unresolved.",
  "candidates": [
    {"status": "reported", "source_id": "source-001", "cell_id": "FIRST",
     "scalar": "FIRST VERBATIM", "units": null, "statistic": null,
     "experimental_condition": "CONDITION A", "comparator": null,
     "row_header_cell_ids": ["ROW A"], "column_header_cell_ids": ["HEADER A"],
     "expected_row_header_text": ["EXACT A"],
     "expected_column_header_text": ["EXACT HEADER A"],
     "condition_cell_ids": [], "expected_condition_text": [],
     "notes": "Candidate A review"},
    {"status": "reported", "source_id": "source-001", "cell_id": "SECOND",
     "scalar": "SECOND VERBATIM", "units": null, "statistic": null,
     "experimental_condition": "CONDITION B", "comparator": null,
     "row_header_cell_ids": ["ROW B"], "column_header_cell_ids": ["HEADER B"],
     "expected_row_header_text": ["EXACT B"],
     "expected_column_header_text": ["EXACT HEADER B"],
     "condition_cell_ids": [], "expected_condition_text": [],
     "notes": "Candidate B review"}
  ]
}
```

Candidate placeholders must be replaced with complete real IDs/text; the schema
uses the same checks as an individual reported value. At least two candidates
must differ in scalar/units/statistic/condition/comparator. Final scalar, primary
paragraph ID, and quote are null; evidence retains all candidates. Units,
statistic, condition, alias, and comparator remain only when common across every
candidate. The conflict is explicitly recorded in claims and uncertainties.

A true duplicate repeated header/cell with identical meaning is not automatically
a conflict. Do not treat simple numeric reformatting as equivalent: preservation
of the discrepancy is safer until semantic review resolves it.

## 4. `extraction_failed`

Use for recoverable or unresolvable evidence-processing limitations:

```json
{
  "field_id": "requested-field",
  "status": "extraction_failed",
  "notes": "Name page/segment, concrete obstacle, and next action (for example visual review of a three-line rowspan)."
}
```

Actionable notes are required. Scalar and value evidence remain null. This is the
default for omitted or rejected bindings. A first geometry-only pass deliberately
leaves every requested field here.

## Accepted-result policy

The engine applies bindings to an in-memory copy. It regenerates claims and
uncertainties, verifies exactly one full field record per target, checks evidence
and status invariants, and writes atomically. If anything fails, no scalar from
the rejected candidate set is promoted. The retained `result.json` identifies the
rejection and remains suitable for inspection and another reviewed pass.
