# The runtime contract, explained for writers

This document explains the execution contract that the
`run-contract-pipeline` skill enforces. Read it once before your first run;
it tells you exactly what the harness expects and what an evaluator can
independently re-check.

## 1. Paths

| Location | Role | Rules |
|---|---|---|
| `/input/case.json` | The case: contract, constraints, material declarations | Read first. Never modify. |
| `/input/task.md` | The writing brief | Read second, in full. |
| `/input/<material>` | Fact base, bibliography, etc., as declared in `case.material` | Read all of it before drafting. Never modify. |
| `/app/work` | Everything intermediate | Plan, contract map, skeleton, evidence table, editable drafts, checkpoints, snapshots, open items. If it is not here, it does not survive an interruption. |
| `/app/output` | Final deliverables | Editable manuscript text + `result.json`. Only assembled, checked artefacts belong here. |

The bundled scripts never hardcode these paths — every script takes explicit
`--case/--work/--output/--draft` arguments. The paths above are the harness
convention; pass them explicitly.

## 2. result.json semantics

`result.json` is the machine-readable statement of what you delivered. Its
shape is dictated by the case itself, not by the skill:

- **`case_id`** — copied verbatim from the input case. A mismatch is a hard
  failure.
- **Every field of the case's `output_contract`** — present, correctly
  nested, correctly typed. The contract values are descriptive strings such
  as `"str, copied from input"`, `"object: path, format, sections[],
  word_counts{}"`, `"array of claim objects (id, section, text, type, refs[],
  quote, source_span, stance, confidence)"`, `"enum: complete | partial |
  blocked"`. `init_run.py` parses these generically into a typed skeleton;
  `assemble_result.py` fills the skeleton only from artefacts that actually
  exist; `contract_check.py` re-verifies types, required subfields, array
  item shapes, and enum membership.
- **`status`** — your honesty anchor:
  - `complete`: the draft exists, is non-empty, and every top-level contract
    field carries real content.
  - `partial`: something is missing. The `limits` list names exactly what
    (machine-readable, e.g. `field_empty:facts_and_sources`,
    `claims_missing`), and `version_and_boundary.open_items` explains why in
    prose.
  - `blocked`: no draft exists at all. The blocker must be stated in
    `limits` and `open_items`.

A field filled with invented content to look "complete" is a worse outcome
than an empty field with an honest `partial`: the former is fabrication, the
latter is a valid deliverable.

## 3. The honest partial

Partial results are first-class citizens of this contract. To produce a good
one:

1. Keep an editable partial draft under `/app/work` from early on — a
   section-level outline with citations already counts.
2. Keep `/app/work/open_items.json` current: a plain list, or an object with
   `changes`, `open_items`, `material_gaps` arrays.
3. Checkpoint after every milestone (`checkpoint.py` appends a JSONL record
   and snapshots files; it is idempotent and append-only).
4. When time runs out: freeze, assemble, check, deliver. `assemble_result.py`
   will compute the status and the `limits` list from what actually exists —
   you never have to (and never should) hand-edit the status.

## 4. What evaluators can independently re-check

Assume the evaluator will re-run mechanical verification. Everything below
must therefore be true of your deliverable without any help from you:

- `case_id` in `result.json` equals the case's `case_id`.
- Every `output_contract` field is present with the declared nesting and
  types; array items carry the declared subfields; `status` is inside its
  enum.
- Word counts: total and per-section (by Markdown headings) against
  `constraints.max_words_*`.
- Distinct Vancouver `[n]` citation markers against
  `constraints.min_distinct_citations`, and — if
  `cite_only_from_bibliography` is set — every cited number resolvable to the
  provided bibliography.
- The rhetorical parts named in `constraints.sections_required` are present
  as recognisable sections/headings, and every topic in
  `constraints.must_cover_topics` appears in the prose.
- Every claim in `facts_and_sources` carries a quote and source span that an
  evaluator can locate in the provided material.

`contract_check.py` performs exactly these checks; run it before the
evaluator does.

## 5. Budgets

Assume **64 model requests, 900 seconds wall-clock, 16384 tokens per
response**. The skill's budget policy:

- Spend model requests on what only the model can do: reading sources,
  selecting claims, writing prose.
- Delegate bookkeeping to scripts: plan/skeleton generation, word and
  citation counting, contract type-checking, assembly, checkpoint snapshots.
- Do not re-run a script that already passed on unchanged inputs.
- Follow the milestone fractions in `plan.json`: read 15% / scaffold +
  evidence 25% / draft 35% / audit + assemble 25%. Reserve the final ~20% of
  runtime for assembly and contract checks; entering that window without a
  frozen draft means delivering a `partial`.

## 6. Incremental saving

The pipeline is interruption-safe by construction:

- `checkpoint.py --work /app/work --stage <name> --snapshot <file>` after
  every milestone. Append-only log at `/app/work/checkpoints.jsonl`;
  snapshots under `/app/work/snapshots/<stage>/`.
- Recovery: read the log, take the newest snapshot, resume. If no time
  remains, assemble from the newest snapshot and deliver an honest `partial`.
- Because the skeleton, plan and contract map are written by `init_run.py`
  at minute one, even a very early interruption leaves a coherent work
  directory that anyone (or any rerun) can pick up.
