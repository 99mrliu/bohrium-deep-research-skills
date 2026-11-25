---
name: field-intent-compiler
description: Compile QUESTION/SCHEMA field intent into explicit pre-candidate acceptance contracts and auditable per-field tests, then validate evidence-bound agent adjudication for reported, not_reported, source_conflict, and extraction_failed results. Use for structured literature-field extraction when exact conditions, statistics, comparators, source scope, conclusion modality, and evidence semantics matter more than literal quote matching.
---

# Field Intent Compiler

## Purpose and boundary

Turn every requested `field_id` into an acceptance contract **before reading candidate values**. The contract covers metric identity, subject/entity, value form, requested unit, statistic, required condition, comparator, source scope, and (for conclusion fields) author modality. Exact quotation validates evidence location only; it is never proof that a candidate answers the question.

This skill governs upstream QUESTION/SCHEMA semantics and adjudication. It is not a PDF text extractor and does not auto-extract, rank, or select values by keywords, number equality, source order, or quote similarity. The agent reads the actual materials and authors every semantic decision. The Python compiler enforces coverage, evidence binding, and decision structure without inventing scientific content.

## Non-negotiable order

1. Read `/input/case.json`, `/input/target-fields.json`, and `/input/task.md` only for case identity, original task, and target QUESTION/SCHEMA.
2. Initialize a complete conservative result skeleton and compile all contracts/tests.
3. Resolve underspecified contract axes from the question/schema **before inspecting source candidate values**.
4. Only then read the source material, construct an exact source-paragraph register, and adjudicate each field against every precompiled test.
5. Record rejected near-matches and unresolved alternatives. Finalize atomically; if finalization fails, preserve the conservative skeleton and repair the identified issue.

Do not reverse steps 3 and 4. Do not retrofit a contract to make a preferred candidate pass. If an amendment is necessary, record its question/schema rationale and re-adjudicate all fields against the new contract hash.

## Runtime workflow

Set `SKILL_DIR` to the directory containing this `SKILL.md`. Python 3.9+ and the standard library are the only requirements; there is no install step and no network access.

### 1. Save the conservative full result immediately

```sh
python3 "$SKILL_DIR/scripts/field_contract.py" init \
  --input-dir /input --work /app/work --output /app/output
```

This writes `/app/output/result.json` with every target field present as `extraction_failed`, null values, and an explicit `Awaiting agent-authored adjudication` reason. It then writes:

- `/app/work/acceptance-contract.json`: all field contracts and pending tests;
- `/app/work/adjudication-template.json`: one placeholder decision per field;
- `/app/work/source-register.json`: initially empty;
- `/app/work/runtime-events.json`: ordered evidence that the skeleton and contracts preceded candidate adjudication.

If initialization fails, retain whatever honest `input_error`/partial artifact was produced and diagnose the named input rather than filling values.

### 2. Inspect contracts before candidates

Every field has ten pre-candidate tests: nine semantic/evidence-scope tests (including modality) plus exact verbatim-evidence integrity. A `blocking_issues` entry means the schema did not explicitly supply an axis; a `reported` or `source_conflict` decision is blocked until that axis is amended. `modality` is automatically `not_applicable` only for non-conclusion fields.

Prefer explicit target-schema axes. Aliases are recognized as documented in `references/adjudication-format.md`, but question prose is **not** silently treated as a fully parsed metric/entity/condition specification. If needed, create an amendments file before source-value review:

```json
{
  "amendments": [
    {
      "field_id": "FIELD_ID",
      "set": {
        "metric_identity": "interpretation grounded in the question",
        "subject_entity": "entity grounded in the schema",
        "expected_value_form": "single numeric scalar",
        "requested_unit": "%",
        "statistic": "mean",
        "required_condition": "all jointly necessary conditions",
        "comparator": "named baseline or none",
        "source_scope": ["SOURCE_ID"],
        "modality": "classify_from_wording"
      },
      "rationale": "Why this reading follows from QUESTION/SCHEMA; no candidate value consulted."
    }
  ]
}
```

Only include axes that need resolution, then run:

```sh
python3 "$SKILL_DIR/scripts/field_contract.py" amend-contract \
  --work /app/work --amendments /app/work/contract-amendments.json
```

Keep `UNSPECIFIED_REQUIRES_CONTRACT_AMENDMENT` unresolved when the task itself is genuinely ambiguous; do not guess. An honest `extraction_failed` with a reason is preferable to a fabricated interpretation.

### 3. Read materials and register exact paragraphs

After contracts/tests are stable, read the actual case materials using the platform's available readers. Create `/app/work/source-register.json` with stable metadata and exact text spans:

```json
{
  "sources": [{"source_id": "SRC1", "title": "actual source title"}],
  "paragraphs": [
    {
      "source_id": "SRC1",
      "paragraph_id": "body-p17",
      "page": 4,
      "text": "The complete paragraph or cell text exactly as captured from the actual source."
    }
  ]
}
```

Use a unique `(source_id, paragraph_id)` pair, preserve page labels (or `null` when unavailable), and do not silently normalize quotes. A paragraph may represent a body paragraph, caption, table cell plus its headers, or supplement paragraph. For table values, include enough header/condition context in the registered text to make the binding independently reviewable. Register rejected candidates too when their rejection is part of the audit.

Unreadable or unavailable material is not `not_reported`. Mark the field `extraction_failed`, state where manual recovery is needed, and preserve work completed elsewhere.

### 4. Author semantic adjudication

Copy the template and author exactly one decision per target field. Bind the file to the current `acceptance-contract.json` hash. See `references/adjudication-format.md` for the complete status-specific structure.

For each `reported` or `source_conflict` decision:

- answer **every** precompiled acceptance test with boolean `passed` and a substantive semantic rationale;
- reject any candidate failing a required test; optionally retain it under `rejected_candidates` with its `failed_test_id` and exact evidence;
- bind primary value and every conflict candidate to an exact registered `(source_id, page, paragraph_id, quote)`;
- preserve `verbatim_value` as an exact substring of `quote` (`72.0` is not silently rewritten as `72`);
- set `scalar` to the agent-adjudicated JSON scalar. A string scalar must equal `verbatim_value`; numeric spellings remain available in `verbatim_value`;
- preserve units, statistic, full `experimental_condition` and comparator. The compiler mirrors `experimental_condition` to `condition`;
- classify conclusion modality as `author_conclusion`, `author_speculation`, `author_limitation`, `reported_fact`, `mixed`, or `unclear`. Preserve hedging and scope rather than upgrading speculation into fact.

The compiler verifies test completeness, failed-test rejection, exact quotes/pages, scope metadata, scalar/evidence shape, and one-record coverage. It deliberately does **not** infer whether semantic prose rationales are scientifically true; that is the agent's evidence-reading responsibility.

### Status-specific rules

- **`reported`**: exactly one primary evidence object; scalar and verbatim value required. A same-number/same-quote candidate under the wrong condition must be rejected, never selected.
- **`not_reported`**: scalar remains null and a `search_record` lists actual in-scope source paragraphs searched plus a rationale. Absence is not zero. A mention of replicate count is not an SD; surrounding text alone does not prove absence.
- **`source_conflict`**: field scalar remains null; preserve at least two distinct `conflict_candidates`, each with its own scalar/condition/evidence. Do not select by source order or invent a priority rule. Multiple semantically valid values at incompatible conditions or unresolved versions belong here.
- **`extraction_failed`**: scalar remains null and `failure_reason` explains the concrete readability, access, parsing, ambiguity, or processing failure. Optional exact evidence can locate the failed material. This is distinct from a completed search that finds no report.

For an honest partial case, do not discard unresolved fields or fill missing arrays with guesses.

### 5. Compile final result and audit

```sh
python3 "$SKILL_DIR/scripts/field_contract.py" finalize \
  --work /app/work --output /app/output \
  --source-register /app/work/source-register.json \
  --decisions /app/work/adjudication.json
```

Outputs:

- `/app/output/result.json`: required `case_id`, `status`, `result`, `claims`, and `uncertainties`, plus `sources` and `change_records`;
- `/app/output/contract-audit.md`: human-readable pre-candidate contracts, tests, decisions, rejections, conflicts, evidence, and uncertainties.

`result.fields` and `result.field_results` are identical complete arrays, one record per requested `field_id`. Overall status is `answered` when all fields have completed adjudications and at least one is `reported`; any `extraction_failed` with at least one reported field gives `partial`; no reported fields gives `insufficient_evidence`; unusable input is `input_error`. Scoped `not_reported` and documented `source_conflict` are completed decisions, not pending work.

The compiler validates every field before replacing result JSON. If it exits nonzero, read the error, keep the conservative result, fix the decision or evidence, and rerun. Never bypass a failed semantic test by changing its rationale to `passed` without actual source support.

## Final self-check

1. Compare field IDs and counts against `/input/target-fields.json`; both mirrored arrays must match exactly.
2. Verify every reported/conflict quote against the actual source paragraph, including page and units; spot-check original material, not only the register.
3. Re-read each condition and comparator end-to-end; reject decoys with the right number but wrong condition, arm, time point, statistic, entity, or modality.
4. Check `verbatim_value`, numeric spelling, error/range/statistic type, and conclusion hedging. No unrequested unit conversion or derived value is presented as reported.
5. Ensure `not_reported` has a real search record, conflicts retain both candidates, and failures have actionable reasons.
6. Confirm claims link to evidence and all unresolved fields appear in uncertainties. Preserve a partial result rather than fabricating completion.

## Runnable synthetic verification

From the skill directory:

```sh
sh examples/minimal/run.sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_field_contract.py
```

The example is entirely **SYNTHETIC**, not an official case or prepared test answer. It demonstrates a same-`72%` wrong-temperature decoy rejection, correct `reported`, `not_reported`, unresolved `source_conflict`, `extraction_failed`, and speculative conclusion modality. Generated files are under `examples/minimal/output/`; exact commands and observations are in `examples/minimal/INSPECTION.md`.

## Limits

- This is not a replacement for reading source material, table reconstruction, PDF/OCR extraction, or expert scientific adjudication.
- Python cannot prove the truth of agent-authored semantic pass rationales. It proves contract coverage and exact registry binding; an agent can still make an incorrect semantic judgment. Original-source spot checks remain necessary.
- Source-scope logic is exact for source-ID lists and the documented all-source strings; complex scopes rely on the semantic test and may need external procedural controls.
- The compiler performs no unit conversion, significance inference, image digitization, or automatic conflict resolution. Preserve source values or mark uncertainty.
