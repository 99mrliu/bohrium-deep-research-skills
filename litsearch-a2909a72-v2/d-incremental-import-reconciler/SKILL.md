---
name: incremental-import-reconciler
description: Stateful, auditable reconciliation of new literature snapshots against an organizer-local prior import state. The engine discovers the prior import state (import_state*.json / *state*.json / library*.json, or case.json keys import_state/already_imported/existing_library), normalizes the new candidate pool (Crossref/EuropePMC/OpenAlex shapes), fingerprints every record, and classifies each candidate ALREADY_IMPORTED / UPDATED / NEW / CONFLICT / SUSPECT with a documented precedence and reason codes. Only NEW and UPDATED are applied — UPDATED with a field-level diff and a JSONL change record; identity conflicts (same DOI, contradictory title; same normalized title, different DOI) are queued for human resolution and never auto-merged; a corrupt prior state aborts loudly instead of silently re-importing everything. A --verify-idempotent flag re-executes the same pool against the written updated_state.json and proves the second pass is change-free. A contract-driven builder fills result.json with the original case_id and every output_contract field. Use for 学术文献检索/literature-search cases whose inputs explicitly include organizer-local incremental import states and where re-imports, silent overwrites and identity auto-merges are the scoring-critical mistakes.
---

# incremental-import-reconciler — reconcile the pool against the state, prove it idempotent

Philosophy: **when a case ships an organizer-local import state, retrieval is no
longer a stateless search — it is a stateful import, and the expensive mistakes
are state mistakes.** Re-importing what is already there (duplicate work,
double-counted evidence), silently overwriting metadata that changed upstream
(undetected corrections), and auto-merging identity conflicts (one DOI, two
titles) are the three ways an import run quietly destroys trust. This skill
makes the import a first-class, auditable operation: every candidate gets an
explicit classification with a reason code, every applied change gets a change
record, conflicts wait for a human, and a second pass over the written state
must provably change nothing.

The agent contributes judgment (reading the case, resolving conflicts,
explaining gaps); the engine does everything mechanical deterministically,
offline, stdlib-only.

## Runtime contract

- Platform installs this skill at `/skills/weekly-skill` and runs fixed cases:
  input `/input/case.json` + `/input/task.md` (+ snapshot material and a prior
  import state), work under `/app/work`, deliverables under `/app/output`,
  including `result.json` with the original `case_id` and **every** field named
  by `output_contract`.
- First action in any run: `ls -R /input` and read `case.json` — note
  `case_id`, every `output_contract` field name, and whether a prior import
  state (file or embedded key) is actually present.
- Save a partial `result.json` before reconciling; improve incrementally; keep
  `status=partial` whenever anything material is unresolved (queued conflicts
  count as material).

## Procedure

1. **Secure a partial result immediately:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status partial
   ```

   (If the skill landed elsewhere, locate it with `ls /skills/*/scripts/`.)

2. **Locate the prior import state before touching the pool.**
   The engine discovers it automatically (see `references/methodology.md` for
   the exact rules): state-shaped filenames under `/input`, or the
   `import_state` / `already_imported` / `existing_library` keys of
   `case.json`. If discovery reports mode `initial`, that means **no prior
   state was found** — say so in `uncertainty`; do not pretend an incremental
   run happened. If the engine aborts with exit 3, the state file is corrupt:
   never delete or bypass it to force a fresh import — that would re-import
   everything. Record the defect and deliver partial.

3. **Run the reconciliation engine with idempotency verification:**

   ```
   python3 /skills/weekly-skill/scripts/reconcile.py \
       --case /input/case.json --input /input \
       --out /app/output --verify-idempotent
   ```

   It prints a one-line JSON digest (mode, state entries, candidates,
   already_imported/updated/new/conflicts/suspects) followed by the
   idempotency line. Exit 2 means the candidate pool was empty — deliver
   partial with the digest in `uncertainty`. `--verify-idempotent` is a real
   second execution: it reloads the just-written `updated_state.json` from
   disk, re-classifies the same pool, and must print
   `IDEMPOTENT: second pass = 0 adds, 0 updates`; anything else exits 1 and
   prints the offending diffs. (Add `--corpus /app/work/corpus` if you saved
   extra raw snapshot responses there with your own tools — never hand-edit
   them.)

4. **Read the artifacts, act only on what they say.**
   - `import_manifest.json` — the ordered decision ledger with reason codes
     and fingerprints; this is the authoritative record of what happened.
   - `reconciliation_report.md` — counts, UPDATED diffs rendered readably
     (e.g. `year: 2021 → 2020`), the conflict queue with both records side by
     side, suspect exclusions, honest notes.
   - `change_records.jsonl` — one JSON object per applied add/update, with
     provenance `{file, json_index}`.
   - **Conflicts are yours to resolve, not the engine's.** For each queued
     conflict, decide from the case context which identity is authoritative;
     state the decision and rationale in `uncertainty` (or fix the pool at the
     source if a saved file is demonstrably truncated) and re-run once. Never
     hand-edit `updated_state.json` or the manifest — fix inputs and re-run.
   - **Suspects** (`NO_IDENTIFIER`, `YEAR_IMPLAUSIBLE`) are excluded, not
     repaired; if one looks important, note it in `uncertainty`.

5. **Finalize and validate:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status success
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --validate
   ```

   Fill any unmapped contract field with `--set 'field=/app/output/<file>'`.
   Keep `--status partial` with `--uncertainty "..."` while conflicts remain
   queued, suspects were excluded, the state was missing (initial mode), or
   the pool was empty. The validator fails loudly on empty contract fields,
   `case_id` mismatch, dangling paths, or `success` with non-empty
   uncertainty.

## What the reconciler guarantees (do not break these)

- **No silent merges:** identity conflicts are queued with both records shown;
  the state is byte-unchanged for every queued conflict. The engine will not
  pick a winner.
- **Every applied change is ledgered:** if it is not in
  `change_records.jsonl`, it did not happen; skips and exclusions carry reason
  codes, not silence.
- **Provable idempotency:** the same pool reconciled against the produced
  `updated_state.json` yields zero adds and zero updates — verified by a real
  second execution, not claimed.
- **No fabrication:** records come only from local snapshot files; missing
  metadata stays `null`; a corrupt prior state stops the run instead of being
  replaced by an empty one.
- **Traceability:** every candidate and change carries `{file, json_index}`;
  `evidence/evidence_index.json` hashes every consulted file.

## Exception handling

| Situation | Handling |
|-|-|
| No prior state found anywhere | Engine runs in `initial` mode; everything classifies NEW. State this plainly in `uncertainty`; do not claim an incremental reconciliation. |
| State file corrupt / malformed | Engine exits 3 with a FATAL message. Do **not** delete or bypass the file (that silently re-imports everything). Deliver partial; defect goes to `uncertainty`. |
| Empty candidate pool | Engine exits 2 with `ENGINE_STATUS=partial`; artifacts are still written with an unchanged state copy. Deliver partial with the digest in `uncertainty`. |
| Queued conflicts at finalize time | Keep `status=partial`; list each conflict and its reason code in `uncertainty`. Only mark `success` after a documented human resolution and a clean re-run. |
| Idempotency check fails (exit 1) | A real bug or a mutated state file — read the printed diff, fix the cause, re-run. Never ship without the zero-change line. |
| result.json validation fails | Fix exactly the reported field with `--set`; never blank a contract field. |

## Resources

- `scripts/reconcile.py` — state discovery, pool normalization, classification,
  application, idempotency verification (stdlib only, offline).
- `scripts/make_result.py` — output_contract-driven result.json
  assembler/validator.
- `references/methodology.md` — state discovery rules, fingerprint definition,
  classification precedence, conflict policy, idempotency semantics, known
  limits — so each decision can be defended.
- `references/selfcheck.md` — pre-submission checklist.
- `examples/minimal_example.md` — a real local run on a synthetic case
  (outputs marked as synthetic example, not a formal case result), including
  the idempotency line.
