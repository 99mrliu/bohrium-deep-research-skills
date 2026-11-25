---
name: numeric-provenance-ledger
description: Harvest every recognizable numeric lexical expression into an append-only exact-offset ledger, then have the Agent select ledger IDs semantically and mechanically verify lossless scalar, unit, statistic, condition, conflict, absence, and unreadability provenance without similarity-based answer selection.
---

# Numeric Provenance Ledger

Use this Skill for literature data extraction where numeric meaning must survive verbatim: scalar values, ranges, inequalities, ± uncertainty, scientific/unit typography, percent versus percentage points, n/p/CI statistics, table/figure references, experimental-condition binding, and conflicting or absent readings. It is intentionally **not** a generic field-candidate ranker.

## Non-negotiable behavior

1. Read the actual `/input/case.json`, `/input/target-fields.json`, `/input/task.md`, and supplied materials. Never assume a value from a field name or domain label.
2. Write `/app/output/result.json` immediately as an honest partial with one placeholder per target, then improve it only from readable evidence.
3. Preserve exact source strings and offsets. No unit conversion, numeric normalization, calculated proxy, guessed missing value, averaged conflict, Unicode cleanup, or casually copied rounded value.
4. Harvest first; choose second. The Agent reads target semantics and ledger/source context and selects ledger IDs. Scripts never choose a reported answer by similarity, first match, proximity, extremum, or plausibility.
5. Keep `not_reported`, `source_conflict`, and `extraction_failed` distinct. Unreadable text is not absent. An absent value is not zero. Different conditions are not a same-condition conflict.
6. Finish with exact ledger reconstruction, a mechanical `check`, and a readable audit. A literal quote alone does not establish semantic correctness.

All Python code is portable Python 3.9+ standard library. No installation, network, model service, personal path, or third-party package is required. Commands below are run from the installed Skill root.

## Runtime workflow

### 1. Read scope and initialize before extraction

Inspect input structure and requested field definitions. Preserve their order and IDs. Run:

```sh
python3 -B scripts/numeric_result.py init \
  --case /input/case.json \
  --targets /input/target-fields.json \
  --output /app/output/result.json
```

This writes `status: partial` and one `extraction_failed`/`pending_read` record per requested field. Leave this file in place if later processing fails; update notes with the concrete failure when possible. Malformed input produces `input_error` rather than fabricated field answers.

Target JSON may be a list of field objects/ID strings or an object with `fields` or `target_fields`. Each object needs `field_id` (`id` is accepted as an input alias). `case.json` needs a nonempty `case_id`.

### 2. Build an exact canonical source layer

Inventory all task-scoped body, table, figure-caption, and supplement material. Use available runtime readers for actual PDFs/text, inspect extraction quality, and create `/app/work/sources.json` in the schema documented in [references/source-ledger.md](references/source-ledger.md).

Each paragraph record contains `source_id`, stable `paragraph_id`, `page` (or `null`), and exact `text`. Preserve headers/conditions with table values and captions with figure-relevant values. Do not use a pre-assumed answer layer. Do not Unicode-normalize superscripts, dashes, `±`, `×`, `·`, `µ`, or `μ`.

If a needed scanned/table region is unreadable, do not invent transcription. Preserve any other usable paragraphs and select `extraction_failed` with `no_text_layer`, `ocr_unreadable`, `parse_error`, or `unreadable_source` for affected targets.

### 3. Harvest the append-only numeric ledger

```sh
python3 -B scripts/numeric_ledger.py \
  --sources /app/work/sources.json \
  --ledger /app/output/numeric_ledger.jsonl \
  --audit /app/work/ledger_inventory.md
```

Inspect both text and inventory for omissions, incorrect units, row/column detachments, residuals that are identifiers rather than measurements, and decoy values. Each row records exact raw text and Unicode-codepoint half-open offsets, scalar/component/unit spans, statistic/comparator, page/paragraph/statement, context, and paragraph hash.

The ledger is append-only. An unchanged rerun appends zero rows. Never hand-edit, renumber, delete, or overwrite existing rows. If corrected source text collides with existing IDs, investigate and use a fresh ledger plus fresh semantic selections rather than rewriting provenance.

### 4. Select IDs by meaning, not by score

Read every target against the source and ledger. Write `/app/work/selection.json` using [references/selection-result.md](references/selection-result.md).

For each target:

- Choose a scalar-bearing `value_token_id` only after quantity, cohort, condition, time point, and comparator match the target. Explicitly rule out decoy values under other conditions.
- Select numeric `condition_token_ids` from the same source statement. Multiple adjacent condition tokens retain the exact intervening text.
- Bind any n/p/CI `statistic_token_ids` and table/figure `reference_token_ids` by reading their context, not because they are nearby.
- Preserve the full scalar form: range endpoints and `±` uncertainty stay in `scalar`, typography stays in `units`, and p/n/CI stays in `statistic`.
- For semantic absence, use `not_reported` with exact scoped `coverage` quotes and inspected-search notes. A regex miss is not evidence of absence.
- For applicable disagreement, use `source_conflict` with all exact variants under identical lexical conditions. Leave top-level scalar/unit/statistic null.
- For unreadable, missing, or ambiguous processing, use `extraction_failed`, a concrete `failure_kind`, mandatory notes, and evidence if readable.

There is exactly one selection per requested field ID. Do not omit a hard field or add an unrequested field result.

### 5. Build final artifacts

```sh
python3 -B scripts/numeric_result.py build \
  --case /input/case.json \
  --targets /input/target-fields.json \
  --sources /app/work/sources.json \
  --ledger /app/output/numeric_ledger.jsonl \
  --selection /app/work/selection.json \
  --output /app/output/result.json \
  --audit /app/output/audit.md
```

The builder reads only selected ledger representations, creates evidence quotations/spans and claims, preserves conflict alternatives, records selection/ledger hashes, and emits the complete output contract. It does not infer an answer from target wording.

### 6. Verify and inspect

Run the independent reconstruction check:

```sh
python3 -B scripts/numeric_result.py check \
  --case /input/case.json \
  --targets /input/target-fields.json \
  --sources /app/work/sources.json \
  --ledger /app/output/numeric_ledger.jsonl \
  --selection /app/work/selection.json \
  --output /app/output/result.json \
  --audit /app/output/audit.md
```

`check` must return zero and must never repair the result. Read `/app/output/audit.md` against the sources and targets. Confirm each requested ID occurs exactly once; both `experimental_condition` and `condition` agree; each reported scalar/unit/statistic/quote is verbatim; percent and percentage points remain distinct; absent/unreadable/conflicting readings have the right status and explanations.

Apply [references/verification-policy.md](references/verification-policy.md) for the semantic checklist and limitations. Mechanical consistency cannot prove that an Agent selected the semantically correct same-sentence clause or performed an exhaustive absence search.

## Output contract

Top level: `case_id`, `status`, `result`, `claims`, `uncertainties`, `sources`, `change_records`.

Overall `status`: `answered` when every field has a completed adjudication (`reported`, scoped `not_reported`, or documented `source_conflict`) and at least one value is reported; `partial` when any field remains `extraction_failed` but at least one is reported, including an early pending skeleton; `insufficient_evidence` when no value is reported and fields are failed or all are scoped non-reports; `input_error` for invalid input.

`result.fields`: exactly one record per target with `field_id`, `status` (`reported|not_reported|source_conflict|extraction_failed`), `scalar`, `units`, `statistic`, `experimental_condition`, `condition`, `comparator`, `paragraph_id`, `quote`, `evidence`, `notes`, and `ledger_ids`. Every evidence item has `source_id`, `page`, `paragraph_id`, and exact `quote`, plus statement/token/span details. Conflicts add full `conflicts`; failures add `failure_kind`. If `result.field_results` is mirrored it must exactly equal `fields` (this Skill normally emits only `fields`).

Null scalar/unit/statistic values are mandatory for unresolved top-level field records. Conflict alternatives live in `conflicts`, not in a fabricated average or converted scalar.

## Explicitly synthetic runnable example

The included example is **SYNTHETIC**, not a formal case, expected answer, benchmark score, or real-paper claim. It contains a 25 °C control decoy, a treated 37 °C value, a cross-source conflict, explicit non-reporting, unreadable-status tests, superscript-minus scientific notation, an en-dash range, `±`, `p<`, `n=`, CI, percent, percentage points, and table/figure references.

From the Skill root:

```sh
python3 -B scripts/numeric_ledger.py \
  --sources examples/minimal/input/sources.json \
  --ledger examples/minimal/output/numeric_ledger.jsonl \
  --audit examples/minimal/output/ledger_inventory.md

python3 -B scripts/numeric_result.py build \
  --case examples/minimal/input/case.json \
  --targets examples/minimal/input/target-fields.json \
  --sources examples/minimal/input/sources.json \
  --ledger examples/minimal/output/numeric_ledger.jsonl \
  --selection examples/minimal/selection.json \
  --output examples/minimal/output/result.json \
  --audit examples/minimal/output/audit.md

python3 -B scripts/numeric_result.py check \
  --case examples/minimal/input/case.json \
  --targets examples/minimal/input/target-fields.json \
  --sources examples/minimal/input/sources.json \
  --ledger examples/minimal/output/numeric_ledger.jsonl \
  --selection examples/minimal/selection.json \
  --output examples/minimal/output/result.json \
  --audit examples/minimal/output/audit.md
```

Run all positive/negative stdlib tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
```

Tests alter scalars, units, condition text, condition IDs, and decoy value IDs and require rejection; they also test append-only byte preservation, exact typography, residual digits, early partial output, conflicts, absence, and unreadability. Actual commands/results and artifact inspection are recorded in [examples/minimal/INSPECTION.md](examples/minimal/INSPECTION.md).
