# Runtime contract, exception handling, and audit checklist

## Required reading and output

Inputs are `/input/case.json`, `/input/target-fields.json`, `/input/task.md`, and supplied paper/artifacts. Work files belong in `/app/work`; final `result.json`, `graph.json`, `evidence-map.md`, and optional `validation.json` belong in `/app/output`. Save `result.json` early and improve it only from actual source reading.

Preserve the input `case_id`. Allowed run statuses: `answered`, `partial`, `insufficient_evidence`, `input_error`. Required top-level keys: `case_id`, `status`, `result`, `claims`, `uncertainties`; sources/change records are emitted for audit.

Every requested target has exactly one entry in `result.fields` and one identical entry in `result.field_results`, in target order. Required field keys:

- `field_id`
- `status`: `reported | not_reported | source_conflict | extraction_failed`
- `scalar`: literal source-faithful value; null when unresolved
- `units`: exact units, including count/dimensionless details where relevant; null if none
- `statistic`: replicates, error, significance, or explicit non-reporting as applicable
- `experimental_condition` and identical alias `condition`
- `comparator`
- `paragraph_id` and `quote`: primary exact location/span
- `evidence`: list of `{source_id, page, paragraph_id, quote}` (page can be null)
- `notes`: field scope, interpretation layer, and inspection handoff

A guessed scalar is forbidden. Missing is not zero. A matching string alone is not semantic verification: entity, conditions, baseline, statistic, attribution, and modality still require reading.

## Initialization behavior and interruption

`prepare_case.py` parses the case and target IDs before reading papers, so an interrupted run still leaves a partial field skeleton. It avoids overwriting an existing result/curated file by default. Review timestamps and change records rather than assuming a placeholder was completed.

If case/target parsing fails, result status is `input_error`, with the recovered case ID when possible and a specific parse/message uncertainty. If sources fail after valid inputs, retain `partial` and classify affected fields as `extraction_failed` rather than `not_reported`.

Build commands are transactional per output file through temporary-file replacement, but the three output artifacts are not one cross-file transaction. After interruption, always rebuild/revalidate the set and inspect case IDs/statuses before delivery.

## Source inventory and extraction

Supported mechanical inputs: PDF, TXT, Markdown, HTML/XML, explicit paragraph JSON/JSONL, and CSV. Control inputs are not mistaken for paper prose. PDF page numbers are registered only from form-feed page extraction; plain text has null pages. Whitespace is normalized in registered text, and all quotes must match that registered representation.

The optional system `pdftotext` is invoked as a subprocess; no Python package installation is needed. It is not bundled. If absent, failing, empty, or garbled:

1. Read warnings and affected source/relative path.
2. Use any available runtime PDF viewer/OCR/table reader to inspect the actual document.
3. Register resulting source paragraphs honestly if your workflow supports that, preserving real page IDs.
4. Otherwise leave affected targets `extraction_failed`, with exact manual handoff (source/page/table where known).

No-text PDF does not justify `not_reported`. Arbitrary JSON string values are not automatically called paragraphs; structured source JSON needs an explicit paragraphs list or source registry.

## Human/agent review of rich paper artifacts

Text extraction can break multi-row headers, merged cells, superscripts, footnotes, and two-column reading order. For a value from a table or figure:

- inspect original layout if available;
- identify row entity, column metric, group headers, footnote selectors, and unit/statistic scope;
- record exact caption/header/footnote spans as additional conditions/evidence;
- register table/caption text with stable paragraph IDs if your runtime extraction creates them;
- do not infer unreadable glyphs or assign a value from visual proximity alone.

Supplementary material is part of the same field scope, not a second-class answer layer. Preserve its distinct `source_id` and real page/paragraph location.

## Error-to-status triage

| Situation | Run/field treatment |
|---|---|
| Malformed case or target list, duplicate field ID | `input_error`; no fabricated answer |
| Missing PDF text layer/OCR unavailable | `partial` or `insufficient_evidence`; affected fields `extraction_failed` |
| Entire permitted source read; requested item absent | `not_reported`, null scalar, scope and nearest evidence |
| Two genuinely incompatible values after scope review | `source_conflict`, null scalar, both observations and locations |
| Different values under different explicit conditions | Separate scoped observations; do not label conflict automatically |
| Quotation not found | Fix curation with exact text/location; never relax source check |
| Claim attribution erased or modality upgraded | Fix kind/scalar/evidence; builder should reject intentional promotion fixture |
| Unexamined supplementary file or unresolved table cross-reference | Partial/extraction failure with handoff; no universal absence claim |

## Final inspection checklist

1. Run `validate_result.py` and require success.
2. Open `result.json`: correct case ID, run status, all target IDs, duplicate-free mirrors, and required keys.
3. Open `graph.json`: no dangling edges; cited/speculative claims retain their kinds and sources; observation-condition edges match output fields.
4. Open `evidence-map.md`: readable, no placeholder text mistaken for data, all caveats visible.
5. Independently compare at least one abstract/conclusion claim, one quantitative observation, one comparator/statistic, and one limitation against the original.
6. Confirm no citation was silently verified and no page/location was inferred.
7. Check `uncertainties` names all unread material, unresolved conflicts, and epistemic boundaries.
8. Update change records to describe any manual correction performed after generation; rerun validation afterward.

## Validation limits

The scripts prove structural coverage, graph consistency, exact membership of quotes in registered paragraphs, value inheritance from observations, and explicit non-promotion constraints. They do not independently understand all scientific language, validate visual table geometry, or prove semantic fidelity. Human/agent source inspection is an essential part of this skill, not an optional embellishment.
