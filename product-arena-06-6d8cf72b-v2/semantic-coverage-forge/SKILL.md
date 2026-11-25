---
name: semantic-coverage-forge
description: >-
  Build task-first, directly useful answers with machine-auditable semantic coverage:
  decompose every explicit question and contract field, test whole-answer evidence
  entailment and checked scope, adversarially review omissions and overgeneralization,
  and apply the exact output contract only as the final structural gate.
---

# Semantic Coverage Forge

Use this skill for question answering, extraction, verification, translation, and section
notes when completeness means **answering what was actually asked**, not merely producing
schema-valid JSON or accumulating citations. The answer matrix is the working instrument;
the delivered `result.json` remains contract-native.

This is not a budget/schema-contract pilot. Do not require paper cards, knowledge graphs,
a citation array, or a fixed research budget for ordinary QA. Schema compliance cannot
repair an unanswered question, an unsupported qualifier, or an overbroad conclusion.

## Runtime and boundaries

At skill runtime:

1. Read `/input/case.json`, `/input/task.md`, and **every actual material file** supplied
   for the case. Inventory files before deciding that something is absent. Do not substitute
   example fixtures for case materials.
2. Use `/app/work` for scratch matrices, extraction notes, and reviews. Use `/app/output`
   for requested deliverables. Write `result.json` with the case's `case_id` and every
   `output_contract` field exactly. Add no helper fields where `additionalProperties` is
   false.
3. Put sources, uncertainty, and change records in contract fields when allowed. Otherwise
   use sidecars such as `/app/output/answer_matrix.json` and
   `/app/output/semantic_review.json`; never smuggle them into a closed result object.
4. Use only platform-provided PDF/document tools for PDFs. Do not use personal paths,
   network access, package installation, or external retrieval to fill gaps.
5. Plan to finish honestly and early: fewer than 64 model calls and under 900 seconds.
   These are ceilings, not targets. If time or information runs out, deliver an explicit
   partial result with precise unchecked scope rather than inventing completion.
6. The bundled example is synthetic and self-contained. It is not case evidence.

## Non-negotiable order

1. Parse the task and contract.
2. Build the answer matrix.
3. Read and map the actual source scope.
4. Draft direct answers and evidence roles.
5. Run adversarial semantic review.
6. Revise, then run the structural contract gate.
7. Preserve a truthful partial result if the semantics and contract conflict.

Never reverse this order by starting with a JSON template and filling whatever is easy.

## 1. Intake: questions and contract are separate inventories

Create two lists before drafting.

### Question inventory

Split every explicit question, subquestion, embedded request, comparison, requested
explanation, and required deliverable field. Preserve:

- the exact requested population, time, location, table/figure/section, and source scope;
- every qualifier and condition (`only`, `if`, `unless`, `exploratory`, `adjusted`, etc.);
- comparator direction and baseline (`lower than B`, not merely `A and B differ`);
- negation and exclusions;
- units, denominators, precision, time points, and whether a number is requested as
  author-reported or may be calculated;
- requested output language and whether translation is scoped to selected text only.

One sentence can contain several obligations. A nested result field is not automatically a
question, and one question can require several result fields; map both directions.

### Contract inventory

Record root and nested `required` fields, property names, types, enums, item counts,
string-length limits, item ID rules, and every `additionalProperties: false`. The actual
`case.json.output_contract` is authoritative whenever that key is present and must be an
object. Every property declared under `properties` must be present in this task workflow,
even if its name was also omitted from `required`. Note required sidecar paths separately.
Do not add convenience fields such as `confidence`, `sources`, `notes`, or `review_status`
to a closed object.

The auditor compares the actual case contract with `plan.output_schema` and any fenced task
schema, emits structural `CONTRACT_DRIFT` for any disagreement, and validates every distinct
supplied schema. A fenced task schema is the fallback authority only when the case contract
key is truly absent; if neither is supplied, the plan schema is the legacy fallback.
`output_contract: null` is malformed, not an invitation to fall back. Never silently choose
the easiest schema.

## 2. Build a machine-auditable answer matrix

Use the structure specified in `references/answer-matrix.schema.json`. At minimum each row
must map:

| Matrix element | Required meaning |
|---|---|
| `item_id` | Stable task/question ID, matching contract item IDs where supplied |
| `question` | One atomic explicit obligation, in the task's meaning not a paraphrased topic |
| `answer_path` | JSON Pointer to the direct answer in `result.json` |
| `status_path` | JSON Pointer to `answered`, `not_reported`, `unreadable`, or `missing`; for a closed direct-answer-only contract, use `null` and matrix-local `answer_status` |
| `evidence_path` | JSON Pointer to evidence, if the contract permits it; otherwise use `null` and matrix-local `evidence` |
| `checked_scope_path` | JSON Pointer to checked scope in the allowed result structure; otherwise use `null` and matrix-local `checked_scope` |
| `evidence_role` | Author-reported, formula-derived from reported inputs, mixed, or context only |
| `checked_source_scope` | Exact source IDs and anchors actually inspected; every evidence source/anchor pair must occur here |
| `inventory_gap` | Required non-empty explanation when a `missing` row legitimately has no source scope to declare |
| `required_answer_terms` | Auditable qualifiers, comparators, negations, values, and units |

Also record relevant derivation formulas, forbidden generalizations, and unresolved
uncertainty. A checked-scope assertion must describe what was actually read; listing an
unread document is not coverage.

The matrix is an audit sidecar, not a license to change the final result shape. Keep paths
as JSON Pointers so the auditor can traverse real output rather than a parallel summary.
For a closed direct-answer-only contract, all three of `status_path`, `evidence_path`, and
`checked_scope_path` may independently be `null`; the auditor then reads `answer_status`,
`evidence`, and `checked_scope` from that matrix row. It validates sidecar evidence and scope
with the same source, anchor, quotation, role, and coverage checks. Sidecars never relax the
result's closed schema.

## 3. Answer first; evidence must entail the whole answer

Each answer begins with the answer itself, in the requested language. Do not make the user
infer a comparison from two numbers or infer a negative from an empty evidence list.
Citations, source IDs, and explanation follow the direct answer only where the contract
allows them.

For every answer, test:

> Does the quoted source text, at the stated anchor, jointly support **all** material
> assertions in this answer, including qualifiers, comparator direction, conditions,
> units, population, and scope?

Topic similarity is insufficient. If an answer combines three claims, one quote supporting
only the first claim is not whole-answer entailment. Split the answer or supply distinct
supporting evidence for each claim. Do not silently expand a table-row result into a
paper-wide or universal conclusion.

### Reported versus derived

Label author-reported values as reported. For a derived value:

1. quote the reported inputs and their units/conditions;
2. record the formula and rounding in the matrix or allowed explanation field;
3. distinguish the calculated result from an author-reported result in wording;
4. ensure the conclusion does not acquire a significance claim absent from the source.

For example, a calculated difference of 1.3 minutes is not an author-reported 1.3-minute
effect merely because the source reports 8.1 and 9.4 minutes.

### Conflicts are two-sided

When sources or passages conflict, report both positions with their respective scope,
conditions, and values. Do not resolve a conflict by citing only the preferred side. If the
task asks for adjudication, explain the basis and remaining uncertainty; otherwise state
that the sources conflict. Check whether apparent conflicts arise from different time
points, populations, definitions, or units before calling them contradictory.

## 4. Absence states are different

Use the most precise status allowed by the task:

| Status | Meaning | Required documentation |
|---|---|---|
| `answered` | The inspected source directly supports the answer, with derivation identified if used | Supporting quote(s) where allowed and exact scope |
| `not_reported` | Relevant, readable material was checked in a defined scope and does not report the requested item | Enumerated source IDs/anchors checked, relevant near-miss information, and no implication of worldwide absence |
| `unreadable` | Relevant material exists but needed content cannot be read reliably (for example, a damaged page or illegible table) | What was unreadable, what remained readable, attempted platform tool, and unchecked consequence |
| `missing` | A required or relevant source/material is absent from the supplied case | Exact missing material and what was available; do not call this `not_reported` |

`not_reported` is scoped to the checked material, not a claim that no source anywhere has
reported the fact. Do not use an SEM, standard deviation, p-value, or range as a confidence
interval. Do not calculate a requested reported CI unless the task permits derivation and
the assumptions are explicit. `checked_source_scope` must stay non-empty for `answered`,
`not_reported`, and `unreadable`. It may be empty only for `missing`, and only when the matrix
row supplies a non-empty `inventory_gap` explaining the absent source/material inventory.
A well-formed quote at a source/anchor pair outside that declared scope produces
`EVIDENCE_OUTSIDE_CHECKED_SCOPE`; it is not accepted as automatic support.

### Closed evidence arrays and `minItems: 1`

Never fabricate evidence to satisfy an array minimum. If a requested item is
`not_reported`, an empty evidence array may be semantically correct. When the contract sets
`evidence.minItems = 1` for that same item:

1. record checked scope in an existing allowed field, such as `checked_scope` or a permitted
   sidecar;
2. keep the evidence array empty and flag the semantic/contract conflict explicitly;
3. return an honest partial/structural failure rather than a topic-only quotation, a fake
   evidence ID, or an assertion that absence itself is a quotation;
4. if the task provides a sanctioned non-evidence placeholder type, use only that explicit
   mechanism and still describe checked scope.

The auditor deliberately does **not** demand evidence for `not_reported`, `unreadable`, or
`missing`; it demands checked scope. Structural schema failures remain visible.

## 5. Adversarial semantic review

Review the draft as an opponent, using `references/semantic-review-checklist.md`. At minimum
make these independent passes:

1. **Omission:** Has every explicit question, subquestion, required field, qualifier, time,
   population, unit, and requested explanation been answered? Look for hidden conjunctions.
2. **Comparator:** Is the direction, baseline, absolute/relative distinction, and unit right?
   Does the answer say more than “different” when direction was requested?
3. **Negation:** Are `not`, `no`, `except`, `unless`, and non-inferiority/non-significance
   preserved? Has absence of evidence become evidence of absence?
4. **Condition:** Are site-, subgroup-, endpoint-, dose-, time-, adjustment-, and
   analysis-set restrictions attached to every applicable clause?
5. **Unsupported generalization:** Does the answer exceed the checked table, population,
   source, or time point? Search for `all`, `universal`, `proves`, `safe`, `effective`, and
   causal or significant language not licensed by the source.
6. **Whole-answer entailment:** For each evidence item, read quote and answer side by side.
   Mark unsupported clauses, not merely unsupported citations.
7. **Conflict symmetry:** Are both sides and their scopes represented?
8. **Derivation:** Are formula inputs, arithmetic, rounding, and reported/derived wording
   distinct?
9. **Usefulness:** Can the user act on the direct answer without reconstructing it from the
   citations? Is necessary uncertainty adjacent to the answer?
10. **Status integrity:** Are `not_reported`, `unreadable`, and `missing` accurate and scoped?

Record findings and resolutions in `semantic_review.json` or `.md` where allowed. A clean
machine audit means only that checks passed; it is not an automatic truth certification.

## 6. Adapt to the task without forcing QA machinery

- **Section notes:** Preserve the source's original section hierarchy, order, headings,
  tables, and topical scope. Note what each section actually contains. Do not reorder notes
  into Q1/Q2/Q3 unless requested, and do not append an unrelated summary.
- **Extraction:** Extract only requested fields and source scope. Preserve exact units,
  labels, missing values, and qualifiers. Do not add a narrative synthesis or paper card.
- **Verification:** Decompose the claim into atomic propositions and assess each against
  the allowed sources. Distinguish supported, contradicted, mixed, and unchecked; an exact
  quote match is only a retrieval check, not automatic truth.
- **Translation:** Translate only the requested span/sections into the requested language.
  Preserve structure, negation, comparator direction, qualifiers, numbers, units, and
  uncertainty. Do not add a summary, commentary, citations, or content outside translation
  scope. Keep unavailable text explicitly marked rather than guessing.
- **Ordinary QA:** No mandatory paper cards, graphs, bibliographic essays, or evidence
  arrays beyond the actual contract. A concise direct answer plus the required support and
  scope is sufficient.

## 7. Final gate and result delivery

Run semantic review before structural validation, then resolve all safe semantic findings.
Finally validate the exact task schema, including nested objects and arrays, required keys,
enum values, lengths, counts, closed properties, and item IDs. Confirm `case_id` against the
actual case.

`result.json` contains only contract-native content. Sidecars may contain the matrix,
review, source/uncertainty log, and change records. Change records should state what changed
and why (for example, “restricted Q2 to Reed site after condition review”), not merely that
a file was edited.

If a requirement cannot be met, preserve the best direct answer and mark its actual status,
checked scope, and unresolved contract issue. Do not convert uncertainty into a plausible
statement to obtain `PASS`.

## Auditor

The Python 3.9+ standard-library auditor is `scripts/semantic_coverage_auditor.py`.
It accepts explicit paths and never discovers or substitutes case data implicitly:

```bash
K=/skills/weekly-skill  # 若实际安装路径不同，设为本 SKILL.md 所在目录
PYTHONDONTWRITEBYTECODE=1 python3 "$K/scripts/semantic_coverage_auditor.py" \
  --plan /app/work/plan.json \
  --result /app/output/result.json \
  --case /input/case.json \
  --task /input/task.md \
  --source /app/work/source_index.json \
  --report /app/output/audit_report.json
```

Repeat `--source` for multiple JSON source indexes. Each source index has `source_id` and
either `text` or `sections`, where each section has a unique `anchor` and `text`. Evidence
quotes must be exact substrings at their declared anchors, and each evidence source/anchor
pair must also occur in the row's `checked_source_scope`; otherwise the semantic finding is
`EVIDENCE_OUTSIDE_CHECKED_SCOPE`.

### Supported output-schema subset

The auditor recursively accepts only these validation keywords:

- all types: `type`, `const`, `enum`;
- objects: `properties`, `required`, `additionalProperties`, `minProperties`,
  `maxProperties` (and this task requires every declared property to be present);
- arrays: `items`, `minItems`, `maxItems`, `uniqueItems`;
- strings: `minLength`, `maxLength`, `pattern` (Python regular-expression semantics);
- numbers: `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum` (numeric forms);
- inert annotations: `$schema`, `$id`, `title`, `description`.

`type` may be one of `object`, `array`, `string`, `boolean`, `null`, `number`, or `integer`,
or a non-empty array of those names. Schemas must be objects. `$ref`, `$defs`, `anyOf`,
`oneOf`, `allOf`, `not`, conditional keywords, `format`, and every other unlisted keyword
are rejected with exit code 2—even when nested under an unvisited property or item. Inline
supported schemas rather than using references or composition. The recursive guard prevents
an unsupported construct from passing as a silent no-op.

The reference matrix schema describes plan/sidecar authoring; it is not an expansion of the
output-contract subset above.

Exit codes:

- `0`: no structural failure; semantic findings may still require human review;
- `1`: structural contract/item-ID failure;
- `2`: malformed input, unreadable file, invalid plan pointers, or CLI usage error.

The report separates `structural_status: FAIL` from
`semantic_status: NEEDS_HUMAN_REVIEW`. With no semantic findings, semantic status is
`NOT_AUTO_VERIFIED`, deliberately not `TRUE` or `VERIFIED`. Quote-at-anchor, required term,
placeholder, and status/scope checks are audits, not proof of entailment or truth.
Human review remains necessary for meaning, completeness, and conflicts.

## Runnable synthetic example

All files under `examples/synthetic` are fictional and labelled synthetic. The example has
exactly three QA tasks: an author-reported mean, a table comparison restricted to one site,
and a `not_reported` 95% CI with an empty evidence array and explicit checked scope.

Run from the bundle root:

```bash
bash scripts/run_example.sh
```

Or supply an output root:

```bash
bash scripts/run_example.sh /app/work/synthetic-output
```

The script writes `result.json`, `answer_matrix.json`, `audit_report.json`,
`semantic_review.json`, and `semantic_review.md` to that root, invokes the real auditor,
and reads back key output values. The default outputs are under
`examples/synthetic/output/`. Q1, Q2, and Q3 have item-specific semantic review records.

Run the standard-library regression suite from the bundle root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

The suite covers case/plan/task drift, fail-closed recursive schema guards, declared-property
presence, out-of-scope evidence (in results and sidecars), sidecar-only closed direct-answer
contracts, conditional empty scopes and inventory gaps, task-only fallback, non-object case
contracts, additional-property failures, and the complete synthetic example.
