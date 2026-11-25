# Evidence-state specification

## Claim unit

A claim is one scalar leaf in one extractor record. Arrays/objects are traversed; their scalar leaves use JSON-pointer-like field paths. CSV/TSV cells remain strings (including blank strings). JSON scalar types are retained as `string`, `integer`, `number`, `boolean`, or `null`.

Each `evidence.jsonl` object contains:

- stable sequential `claim_id` and `record_id` in sorted source/row order;
- extractor `record_source`, `record_locator`, `field_path`, `field_type`, and `observed_value`;
- `state`, human-auditable `reason`, `source_value`, `support_anchors`, `conflicts`, and `missing_or_unusable_anchors`;
- enabled comparison rules and the explicit no-inference comparison statement.

Record and claim IDs identify processing order, not scientific identity. Input-relative paths are used for reproducibility. Every anchor must point to supplied evidence, never to a hypothetical source.

## State semantics

| State | Required condition | Output behavior |
|---|---|---|
| `corroborated` | A nonblank observed value has an independent, readable exact match or a match under explicitly enabled normalization, and no same-field conflict was found. | Retain observed value; apply only enabled normalization with `apply=true`. |
| `source_conflict` | Same-record/same-field evidence exposes a different nonmissing value, whether or not another location coincidentally matches the extractor. | Retain extractor content, expose every detected conflicting value/anchor, queue for adjudication; no silent replacement. |
| `extractor_only` | A nonblank value has no detected support/conflict despite a readable independent source pool, and no source read failure makes the search incomplete. | Retain only as flagged extractor content; queue review. |
| `unverifiable` | The extractor value is null/blank, a matching source says missing/not reported/unknown unit, no independent readable material exists, or supplied source errors prevent a complete search. | Keep blank/null or flagged content unresolved; queue review. |

Conflict has priority over corroboration. Missing extractor values remain `unverifiable` even when a missing-source anchor is present. Unreadable evidence never upgrades a claim. A value's presence anywhere is not proof of scientific correctness; the emitted locator lets a reviewer assess context.

## Independence and association

The candidate's own file is excluded from support and conflict searches. Case/task documents and other material files may support it. A structured record comparison requires an identifier key shared with the candidate and equal under enabled comparison rules. Identifier keys include common `id`, `doi`, `name`, `title`, and `*_id` names. Cross-record fields must also have equal normalized field names. With multiple records, text evidence must mention a candidate identifier. These checks reduce but do not eliminate entity ambiguity.

CSV/TSV files can simultaneously provide row/cell observations and exact text offsets. JSON sources provide pointers and exact serialized scalar values. Text/Markdown supports exact offsets and conservative `field: value` or table-cell interpretation. Markdown emphasis/backticks around labels and values are stripped for comparison, while anchors still cover the original source line.

## Source truth and normalization

No answer key is embedded in code. All source values come from runtime case/task/materials. Extractor and evidence tables are never majority-voted. Different representations such as `182` and `182.0` in string cells are not silently equated, and no units are converted.

Enabled Unicode, case, and whitespace equivalences affect comparison only. Actual output rewriting separately requires `apply: true`, a string observed value, and corroboration. Every actual rewrite produces a `changes.jsonl` record with before/after values and evidence claim ID. Conflicts and unsupported content never receive cleanup merely because normalization is enabled.

## Result uncertainty

Any non-corroborated claim appears in `review_queue.csv` and `result.json.uncertainty`. Unknown contract fields use JSON `null` and are named in `unresolved_fields`; they also make the status partial rather than allowing an otherwise complete run to overclaim success.
