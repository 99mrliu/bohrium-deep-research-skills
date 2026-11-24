---
name: run-contract-pipeline
description: >
  Run a scientific-writing case (introduction / related-work) end to end under
  a harness with strict process quality control: staged checkpoints so partial
  work is never lost, disciplined reading of the case contract, assembly of a
  result.json that mirrors the case's output_contract exactly, honest
  complete/partial/blocked status, and budget-aware execution. Use when asked
  to run a writing case end to end, assemble result.json, manage partial
  deliverables, produce a contract-compliant submission, or keep an
  interruption-safe writing pipeline.
---

# run-contract-pipeline

## Purpose

This skill is the **runtime contract and process quality control layer** for
introduction / related-work writing tasks executed by an agent under a
harness. It does not write the science for you. It guarantees that:

1. You read the case contract before writing anything.
2. Partial work is checkpointed after every milestone, so an interruption
   still leaves a submittable partial result.
3. The final `result.json` mirrors the case's own `output_contract` field by
   field, with correct nesting and types, and carries `case_id` verbatim.
4. The declared `status` is honest: `partial` enumerates exactly what is
   missing, `blocked` states the blocker.
5. Bookkeeping (word counts, citation counts, contract checks, assembly) is
   delegated to deterministic scripts, sparing the model-request budget for
   reading sources and writing prose.

## When to use

Use this skill whenever a task looks like:

- "Run this writing case end to end and deliver `result.json`."
- "Write the introduction / related work for the case in `/input` and submit
  under the case's output contract."
- "Assemble result.json", "manage partial deliverables", "make a
  contract-compliant submission".
- Any writing run where time or model requests may run out mid-task and a
  partial deliverable must still be valid.

## The runtime contract

The harness fixes where things live. Treat these as obligations, not
suggestions:

- **Input** is `/input/case.json` and `/input/task.md`, with material files
  exactly as declared in `case.material`. Read `case.json` first, then
  `task.md`, then every declared material file. Never modify anything under
  `/input`.
- **All intermediate work** goes under `/app/work`: plan, contract map,
  skeleton, evidence tables, editable partial drafts, checkpoint log,
  snapshots, open items. If it is not under `/app/work`, it does not survive.
- **Final deliverables** go under `/app/output`: the editable manuscript text
  and `result.json`.
- **`result.json` semantics**: it carries `case_id` copied verbatim from the
  input case and **every field of the case's own `output_contract`**, with the
  nesting and types the contract describes. The contract values are
  descriptive strings (e.g. `"object: path, format, sections[],
  word_counts{}"`, `"array of claim objects (id, section, ...)"`, `"enum:
  complete | partial | blocked"`); `init_run.py` parses them generically into
  a typed skeleton, and `contract_check.py` re-checks your result against
  that parse.
- **Honest status**:
  - `complete` — the draft exists and is non-empty, and every top-level
    contract field is populated with real content.
  - `partial` — something is missing; the `limits` list must name exactly
    what, and `version_and_boundary.open_items` should say why in prose.
  - `blocked` — no draft exists at all; say what blocked you.
- **Incremental saving**: save an editable partial draft early (even a rough
  section-level outline with citations counts) and checkpoint after every
  milestone. If the run is killed at any point, the last checkpoint plus the
  partial draft must still assemble into a valid `partial` result.
- **Never fabricate**: no invented citations, no invented numbers, no
  invented claims to make fields look populated. An empty field plus an honest
  `partial` is a valid deliverable; a fabricated field is not.

## Budget policy

Assume a budget of **64 model requests, 900 seconds wall-clock, 16384 tokens
per response**. Spend it on the two things scripts cannot do: reading sources
and writing prose.

- Delegate all bookkeeping to the bundled scripts: plan/skeleton creation,
  word and citation counts, section/topic presence, contract type checks,
  result.json assembly, checkpoint snapshots.
- Do **not** re-run a script that already passed on unchanged inputs; keep
  its report and cite it.
- Reserve the **final ~20% of runtime** for assembly and contract checks
  (`audit_assemble` milestone). If you enter that window with an unfinished
  draft, freeze the draft as-is and assemble an honest `partial` rather than
  gambling the whole deliverable on one more rewrite.
- The milestone plan written by `init_run.py` splits time as: read 15% /
  scaffold + evidence 25% / draft 35% / audit + assemble 25%.

## Checkpoint discipline

A checkpoint is cheap; a lost draft is not. The rules:

- Checkpoint at least once per milestone (`read`, `scaffold`, `draft`,
  `audit`), and after every draft section during Stage 3.
- Always snapshot the current draft file, not just a note — the JSONL log
  records *that* you checkpointed, the snapshot preserves *what* you had.
- `checkpoint.py` is append-only and idempotent: re-running it can never
  corrupt earlier checkpoints, so when in doubt, checkpoint.
- Recovery after an interruption: read `/app/work/checkpoints.jsonl` to find
  the last completed stage, resume the draft from the newest snapshot under
  `/app/work/snapshots/`, and continue the loop from there. If no time
  remains, assemble immediately from the newest snapshot as an honest
  `partial`.

## The five-stage operating loop

### Stage 1 — Read the case and the task, then init the run

Read `/input/case.json` and `/input/task.md` yourself. Note
`output_contract`, `constraints`, `deliverables`, and `material`. Then
initialise:

```bash
python3 <skill-dir>/scripts/init_run.py \
  --case /input/case.json --task /input/task.md \
  --work /app/work --output /app/output
```

This writes `/app/work/plan.json` (milestones with time fractions, extracted
constraints, deliverables, contract field names, next_actions checklist),
`/app/work/contract_map.json` (typed parse of every contract descriptor), and
`/app/work/skeleton_result.json`. Review the contract map; resolve any
`needs_manual_review` notes by hand before drafting.

Checkpoint immediately:

```bash
python3 <skill-dir>/scripts/checkpoint.py --work /app/work --stage read \
  --note "case, task, material read" --snapshot /input/case.json
```

### Stage 2 — Evidence and scaffold

- Read every material file declared in `case.material`. Build an evidence
  table (in `/app/work`, e.g. `evidence.md`): one row per claim you may make,
  each with its exact source quote and span. If a reference is title-only, you
  may cite its existence but must not attribute findings to it.
- Fix the citation order (first appearance, per the case's citation style)
  **before** writing prose.
- Create `/app/work/open_items.json` early — either a plain list, or an object
  `{"changes": [...], "open_items": [...], "material_gaps": [...]}` — and keep
  it updated. Anything the material does not support goes here, never into
  the prose.
- Checkpoint with a snapshot of the evidence table.

### Stage 3 — Draft, checkpointing after each milestone

- Write the draft as Markdown under `/app/work` (e.g. `/app/work/draft/
  introduction.md`), with one heading per rhetorical part the case requires
  (background / related work / gap / contributions, or whatever
  `constraints.sections_required` names).
- **Save an editable partial draft early** — after the first section, not
  after the last. Refine in place.
- Respect `constraints`: word limits, minimum distinct citations, required
  topics, cite-only-from-bibliography, no new facts. The auditor will count
  mechanically, so count mechanically first (Stage 4).
- Checkpoint after each milestone with `--snapshot` of the current draft:

```bash
python3 <skill-dir>/scripts/checkpoint.py --work /app/work --stage draft \
  --note "background + related work drafted" \
  --snapshot /app/work/draft/introduction.md
```

### Stage 4 — Audit

- Copy the current draft to its delivery location and audit it against every
  constraint before assembling. Do not eyeball word counts — that is what
  `contract_check.py` is for (you may run it on a provisional result, or read
  the word counts `assemble_result.py` computes into `target_artifact`).
- Verify each claim against the evidence table: every statement about another
  work must be traceable to that work's provided text; every contribution must
  point at an available anchor (figure/section) declared in the case.
- Update `open_items.json` with whatever remains unsupported.

### Stage 5 — Assemble, check, deliver

```bash
python3 <skill-dir>/scripts/assemble_result.py \
  --case /input/case.json --work /app/work --output /app/output \
  --draft /app/work/draft/introduction.md \
  --claims /app/work/claims.json \
  --verification /app/work/verification_report.json   # if you have one

python3 <skill-dir>/scripts/contract_check.py \
  --case /input/case.json --result /app/output/result.json \
  --draft /app/work/draft/introduction.md \
  --out /app/output/contract_report.json
```

- `assemble_result.py` only fills fields from artefacts that actually exist;
  it never invents content. It prints the status and the `limits` list.
- `contract_check.py` exits 0 when nothing hard-fails, 1 on any hard fail.
  A hard fail means the submission is **not contract-compliant**: fix the
  cause (or downgrade the status honestly) and re-check.
- A convenient order is: assemble pass 1 → contract_check → re-assemble with
  `--verification` pointing at the check report → final contract_check. That
  embeds a real verification artefact in `result.json`.
- Deliver the editable manuscript and `result.json` under `/app/output`.
  Keep the original inputs intact.

## Script reference

All scripts are pure Python 3 standard library, take explicit paths (nothing
is hardcoded to `/input` or `/app`), and exit 0 on success, 1 on check
failures, 2 on usage errors.

| Script | Invocation | What it does |
|---|---|---|
| init_run.py | `--case CASE.json --task task.md --work WORKDIR --output OUTDIR` | Writes `plan.json`, `contract_map.json`, `skeleton_result.json` into WORKDIR. |
| checkpoint.py | `--work WORKDIR --stage NAME [--note TEXT] [--snapshot PATH ...]` | Appends a JSONL record to `checkpoints.jsonl`; copies snapshots into `snapshots/<stage>/`. Idempotent. |
| assemble_result.py | `--case CASE.json --work WORKDIR --output OUTDIR [--draft PATH] [--claims PATH] [--verification PATH]` | Fills the skeleton from artefacts that actually exist; computes per-section and total word counts from the draft; sets honest status + `limits`; writes `OUTDIR/result.json`. |
| contract_check.py | `--case CASE.json --result RESULT.json [--draft PATH] --out REPORT.json [--sections-json FILE]` | Type-checks result.json against the parsed contract; verifies constraints against the draft (word limits, distinct `[n]` citations, required rhetorical parts, must-cover topics). Exit 1 on any hard fail. |

Descriptor parsing rules (leading `str` → string; `object:` with `name[]` /
`name{}` subfields; `array of X objects (f1, f2, ...)` with an item skeleton;
`enum:` with allowed values; anything unparseable → `needs_manual_review`,
checked as *not_verifiable*, never silently failed) are documented in the
docstrings of `init_run.py` and `contract_check.py`.

## Failure modes and disposal

Universal disposal rule: **degrade to partial with specific open_items; never
fabricate; keep the original inputs intact.**

| Failure mode | Detection | Disposal |
|---|---|---|
| Material file missing | A path in `case.material` does not exist when you try to read it in Stage 1-2. | Record the missing path in `open_items`; write only what the remaining material supports; assemble as `partial` (or `blocked` if no draft is possible). Do not guess the missing content. |
| Bibliography empty or unparseable | `references.json` parses to zero entries or fails to parse. | Do not cite anything from memory. Record `material_gaps: ["bibliography empty/unparseable"]`; the related-work passage becomes a gap statement grounded in the fact base only; status `partial`. |
| Reference has no abstract (title-only) | Entry lacks an `abstract` field. | You may cite the work's existence and topic (from its title) but must not attribute findings to it. Note it in `open_items` if the case expected more. |
| Unknown citation style | `constraints.citation_style` is absent or names a style you do not know. | Use the bibliography's own numbering and say so in `open_items`; do not invent a style specification. |
| output_contract descriptor unparseable | `init_run.py` prints `WARNING: fields needing manual review`, or `contract_map.json` shows `needs_manual_review` notes. | Hand-write that field's structure from the raw descriptor text; `contract_check.py` will mark it `not_verifiable` rather than failing it. Record your interpretation in `open_items`. |
| Language switch mid-case | `case.language` / `constraints.language_of_output` disagree with `task.md`, or material is in another language than the required output. | Follow `constraints.language_of_output` if present, else `case.language`; note the discrepancy in `open_items`; never silently mix languages in the draft. |

## Honesty and scope

- The bundled example under `examples/` is **synthetic**: every manuscript
  fact, reference, author, journal, DOI and number is invented. It
  demonstrates the interface only.
- **Never submit precomputed answers** (including anything from `examples/`)
  for the organizers' fixed cases. Run the pipeline on the real inputs.
- **Never invent scores, benchmark numbers, or evaluation results** — not in
  the draft, not in `result.json`, not in reports about this skill.

## Limitations

- The checks are **mechanical**: types, counts, keyword presence. They do not
  prove semantic quality, rhetorical flow, or that a citation actually
  supports its sentence. A 100%-pass report means "contract-compliant and
  constraint-compliant", not "good science writing".
- The skill **does not write the science for you**. Source reading, claim
  selection, and prose remain the agent's job. The skill guarantees the
  process and the contract: nothing is lost, nothing is fabricated, and what
  you submit is exactly what the case asked for.
