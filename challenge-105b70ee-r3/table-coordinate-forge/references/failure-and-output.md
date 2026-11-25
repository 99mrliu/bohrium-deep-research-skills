# Runtime, output contract, and failure decisions

## Invocation interfaces

Production defaults (no third-party Python dependencies):

```bash
python3 "$SKILL_HOME/scripts/runtime.py" \
  --input-dir /input \
  --work-dir /app/work \
  --output-dir /app/output
```

After reviewing the candidate geometry, rerun with
`--bindings /app/work/reviewed-bindings.json`. `--pdf-timeout` defaults to 180
seconds per PDF and can be raised for a slow source. Every invocation starts by
writing or retaining a contract-valid result before PDF conversion.

For direct debugging of one existing bbox file:

```bash
python3 "$SKILL_HOME/scripts/layout_forge.py" \
  --bbox DOCUMENT.bbox.xhtml \
  --source-id source-debug \
  --output-dir DEBUG_WORK
```

The debugging command emits candidates only, never field answers.

Validate an existing JSON deliverable independently:

```bash
python3 "$SKILL_HOME/scripts/validate_result.py" \
  --result /app/output/result.json \
  --target-fields /input/target-fields.json \
  --svg /app/output/table-preview.svg
```

All file arguments can be replaced by portable paths in local testing. Production
skill docs intentionally use only runtime-absolute `/input` and `/app` paths.

## Inputs and discovery

- `case.json`: object with non-empty `case_id`; its `output_contract` can add
  case-specific top-level keys. Additional declared keys are initialized to null
  unless this workflow fills them.
- `target-fields.json`: nonempty list, or object containing `fields`,
  `target_fields`, or `targets`. Each object needs `field_id` (legacy `id` is read
  as a fallback) and IDs must be unique. Only identifiers/order are read from this
  file; target values are never copied as answers.
- `task.md`: nonempty UTF-8 instructions copied to work for audit.
- PDFs: recursively discovered under input, processed in sorted path order.
- Supplied coordinate sources: `.xhtml`, plus `.xml` only when its filename also
  contains `bbox`. This avoids mistaking arbitrary XML for Poppler geometry.

With both PDFs and supplied XHTML, PDF source IDs are `source-001`, etc., followed
by supplied coordinate IDs `supplied-bbox-001`, etc. Sources contain relative input
paths, actual byte length, SHA-256, kind, and bbox extraction state. The task card
is labeled non-scientific evidence.

## Early writes and artifact roles

`/app/output/result.json` is initialized before source enumeration. Each field
starts with null scalar/condition/evidence and `extraction_failed`; overall state
can conservatively be `partial` during the unfinished workflow. The final binding
pass uses stricter exhausted-state logic below.

`/app/work` files:

- `task.md`: actual task card copy;
- `source-NNN.bbox.xhtml`: generated coordinates for each PDF;
- `layout.json`: full page/line/word geometry;
- `tables.json`: candidate cells and continuation headers;
- `reviewed-bindings.template.json`: unfinished, editable field template;
- `table-preview.md/svg`: candidate previews.

`/app/output` retains the contract JSON and both preview forms. Previews use
vector/searchable text; no raster renderer is required. Work paths in the result
are basenames relative to the output directory.

## Required JSON shape

Every final result has at least:

```text
case_id, status, result, claims, uncertainties
```

`sources` and `change_records` are included by the supplied runtime. Any extra
keys explicitly required by a case's output contract are retained. No
`field_results` mirror is emitted; if downstream code adds one, it must exactly
mirror `result.fields` rather than drift.

`case_id` is copied exactly. Overall `status` is one of:

| Value | Meaning in this workflow |
|---|---|
| `answered` | Every requested field has a supported reported, not-reported, or conflict decision. This does not mean every scalar is present. |
| `partial` | At least one field is resolved and at least one remains extraction-failed; an early all-unfinished scaffold may also use this conservative state. |
| `insufficient_evidence` | A completed binding effort leaves all requested fields extraction-failed with no resolved decision. |
| `input_error` | Case/target/task shape or required initial input is invalid; error is explicit. |

`result.fields` contains exactly one object per target, in target order. Every
object always contains all keys:

```text
field_id, status, scalar, units, statistic,
experimental_condition, condition, comparator,
paragraph_id, quote, evidence, notes
```

Per-field `status` is exactly:

| Value | Required representation |
|---|---|
| `reported` | Non-empty verbatim scalar string; exactly one primary value-cell evidence item; non-null primary paragraph ID and full-cell quote; complete condition and alias. |
| `not_reported` | Null scalar/paragraph/quote, empty value evidence, scoped absence rationale in notes. |
| `source_conflict` | Null scalar/primary IDs, at least two candidate value-cell evidence items, notes explaining unresolved readings. Common units/conditions may be retained. |
| `extraction_failed` | Null scalar and empty value evidence, actionable extraction obstacle and next review action. |

`units`, `statistic`, `experimental_condition`, `condition`, `comparator`,
`paragraph_id`, `quote`, and `notes` are strings or null. Numeric-looking scalars
remain strings. `experimental_condition == condition` is always enforced.

Each evidence item has at least `source_id`, one-based integer `page`,
`paragraph_id`, and full-cell `quote`. Reported evidence additionally has:

- `location.table_id` and `segment_id`;
- value `row_id`, `column_start`, `column_end`;
- reviewed `row_header_cell_ids` and `column_header_cell_ids`;
- `condition_evidence`: source/page/cell/quote/location for each supporting cell.

A reported field's primary quote and paragraph ID must match its evidence. A
not-reported or extraction-failed field cannot attach value evidence to imply a
reading. A conflict needs two genuinely different reviewed candidates computed
over scalar, units, statistic, condition, and comparator.

`claims` are generated from fields, not unsupported summary prose:

- `field_extraction`: field ID, source, primary and condition evidence, precise
  cell location, statement preserving value/units/condition;
- `source_conflict`: field ID, all evidence and locations.

`uncertainties` repeat field-level not-reported, conflict, and failed reasons and
also retain source/tool problems. `change_records` record actual event timestamps
and whether geometry was reconstructed, bindings applied, or inputs/bindings
rejected; no benchmark score or service state is fabricated.

## Failure decision matrix

| Situation | Overall/field handling | Required next action |
|---|---|---|
| Missing/malformed case, target list, or empty task | `input_error`; initialize valid empty-field result | Correct concrete JSON/task input. |
| Missing `pdftotext`, conversion exit error, or timeout | Partial early result; affected fields remain failed unless supplied geometry supports reviewed bindings | Install Poppler or run the displayed bbox-layout command; supply resulting XHTML. |
| No PDF or bbox input | Partial source-missing result | Supply real materials, not prepared answers. |
| Empty scan text layer | Coordinate/no-table failure | Use an external OCR stage that produces trustworthy word coordinates, then rerun; visual review required. |
| No repeated-gutter candidate | `no_table_candidate`; no auto values | Inspect original layout and improve source coordinates or extend geometry rules. |
| Candidate grid exists but no reviewed binding | `partial`, null scalars | Inspect preview and author exact reviewed bindings. |
| Expected header text, source, ID, unit context, or scalar substring mismatch | Reject binding file, exit 2; preserve partial null scalars and append rejection reason | Reinspect current `tables.json`; update the semantic binding, never bypass validation. |
| Wrapped row/rowspan/footnote cannot establish condition | Affected field `extraction_failed`, not `not_reported` | Original-PDF visual review or geometry extension. |
| Complete scoped review finds no field | `not_reported` with null scalar | Keep reviewed scope and notes; never output zero. |
| Multiple incompatible supported readings | `source_conflict`, no scalar | Preserve all candidate evidence and conditions for adjudication. |
| One or more but not all fields resolved | `partial` | Complete missing fields honestly or leave their failed reasons. |

Exit 0 means the runtime completed its requested pass, even if the resulting
scientific status is partial; exit 2 means input/reconstruction/binding failure.
Callers must inspect JSON status rather than treating process exit 0 as proof that
all values were reported.

## Repetition and determinism

Cell IDs derive from sorted input/source order, page order, candidate segment
order, physical row order, and occupied columns. Reconstructing unchanged input in
the same order should produce the same IDs. `created_at` and `change_records` are
actual timestamps, so whole-file byte equality is not the determinism criterion.
A changed source file, source ordering, or geometry can change IDs; exact expected
text checks intentionally reject stale bindings rather than silently remapping.
