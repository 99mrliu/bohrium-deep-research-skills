---
name: evidence-adjudicator
description: Adjudicate extracted CSV, TSV, and JSON records against case and source evidence with exact locators, typed claims, conflict states, conservative normalization, and contract-complete review artifacts.
---

# Evidence Adjudicator

## Trigger

Use this Skill when the task is to decide which extracted literature-data values are actually supported by supplied evidence, especially when required outputs include cleaned records plus an evidence trail, conflict review, or audit. It handles source disagreement, unsupported extractor values, missing values or units, CSV row anchors, text offsets, JSON pointers, and optional PDF page anchors.

## Non-trigger

Do **not** use it as a generic table formatter, unit-conversion service, chemistry/materials inference engine, PDF OCR pipeline, or catalog-discovery tool. Do not use it to select a plausible value where no supplied source supports that value. A formatting-only job with no evidence adjudication need is outside its scope.

## Runtime contract

Python 3 standard library only for the implementation. `pdftotext` is an optional external reader, not a Python dependency.

```bash
python3 scripts/evidence_adjudicator.py \
  --input /input --work /app/work --output /app/output
```

All three options have exactly those defaults. Overrides are available:

```bash
python3 scripts/evidence_adjudicator.py \
  --input /input --work /app/work --output /app/output \
  --case /input/case.json --task /input/task.md
```

The script creates work/output directories, reads the actual case, task, and input materials, writes a partial artifact set before full processing, and never uses network, time, randomness, hardcoded official labels, or answer data. Input symlinks are skipped.

### Extractor/source selection

- Structured `case.json` declarations `extraction_file(s)`, `extracted_file(s)`, `records_file(s)`, or `candidate_file(s)` take priority for delimited/JSON extractor roles.
- Otherwise file stems containing `extracted`, `extraction`, `candidate`, `submission`, `parsed`, or `record(s)` identify extractor records. Stems containing `reference`, `evidence`, `source`, or `truth` are evidence only. A task-named path with extraction/adjudication wording can also identify an extractor.
- Common embedded collections (`extracted_records`, `extraction_records`, `extractions`, `records`, `rows`, `observations`, `measurements`, and `data`) are extractor candidates.
- An otherwise unlabelled delimited table is also treated as a candidate extraction rather than silently trusted as evidence or discarded. Independent evidence is still required for corroboration. Ambiguous JSON configuration objects are not promoted merely because they are JSON.
- CSV/TSV tables retain header-based values and physical row numbers. Supported JSON extractor shapes are a list of row objects, an object containing `records`/`rows`/`items`/`data`/`extracted_records`/`extractions` lists, or a scalar-only object. Nested scalar leaves receive JSON-pointer field paths.

## Decision policy

Each scalar becomes a typed evidence claim. A record cannot corroborate itself. Structured cross-record comparison requires a shared identifier; a single-record case may use case-level scalar evidence. Exact source substrings and conservative field-labelled text are also considered. Multi-record text evidence must mention an identifier for that record.

States are `corroborated`, `source_conflict`, `extractor_only`, and `unverifiable`; conflict takes precedence over a coincidental exact match elsewhere. Unsupported values remain marked and are never scientifically guessed. Conflict values are not silently replaced. Null/blank fields remain unresolved. See `references/evidence-states.md` and `references/locators.md`.

No normalization is applied by default. Case `normalization`/`normalization_rules` may enable only `trim_whitespace`, `collapse_whitespace`, `unicode_nfkc`, and `casefold` for comparison. Output rewriting additionally requires `apply: true` (or `apply_to_output: true`) and corroboration. Unit conversion and numeric equivalence across different strings are not performed.

## Outputs

Every run attempts all seven files in `--output`:

- `cleaned.csv`: directly readable original fields plus record/state/review/source/unsupported metadata; nested values are canonical JSON strings.
- `cleaned.json`: record data, source record locators, per-field states, and claim IDs.
- `changes.jsonl`: only actual, case-authorized normalizations of corroborated strings.
- `review_queue.csv`: every non-corroborated field, its reason, and serialized evidence references.
- `evidence.jsonl`: typed claims, values, states, conflicts, and exact support/missing anchors.
- `audit.md`: state counts, source hashes/read errors, enabled normalization, review items, and limitations.
- `result.json`: `case_id`, honest `status`, `sources`, `uncertainty`, both `change_records` and `change_log`, `review_queue`, `unresolved_fields`, and relative `artifacts`, plus all fields in `case.output_contract`.

The contract reader accepts a field dictionary, lists of strings, lists of field dictionaries (`name`/`field`/`key`), and nested `fields`/`properties`/`required` structures. Wrapped `case_id` is recovered from common `case`, `metadata`, `case_metadata`, `task`, and `input` objects. Unknown contract values are `null`, named in `unresolved_fields` and `uncertainty`; they are never invented.

`status=success` requires readable processing, at least one extracted record, every claim corroborated, and no unknown contract value. `partial` means valid processing left conflicts, unsupported/missing evidence, read errors, no extractor records, or unresolved contract fields. `input_error` is used for invalid/missing case JSON or task text. Invalid input returns exit 2, unexpected processing failure returns 1, and a completed success/partial adjudication returns 0. Partial artifacts are not deleted on failure.

## PDF and other limitations

PDFs are read only through `pdftotext -layout FILE -` when available. Form-feed-separated text receives 1-based page locators and page-local exact offsets. Missing/failed conversion, empty OCR-less text, or scanned pages remain honestly unresolved; no page or value is invented. Global read failures make otherwise unsupported claims unverifiable rather than corroborated.

This is not fuzzy entity resolution: identifiers/names and field labels must be sufficiently aligned. Exact substring support can be weaker than same-row field evidence, and every reference is therefore exposed for review. No statistical confidence or scientific correctness score is inferred. See `references/maintenance.md` before changing comparison or contract behavior.

## Synthetic example

```bash
bash examples/run.sh
python3 scripts/self_check.py
```

The example is entirely synthetic and deliberately ends `partial`. Its files and generated outputs are visibly marked `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`.
