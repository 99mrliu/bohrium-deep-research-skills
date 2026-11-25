---
name: retrieval-run-warden
description: Process quality control for source-bound literature retrieval runs — an audit warden that makes fabrication impossible to ship and contract violations impossible to miss. The warden does not improve search; it audits whatever the run produced. Every claimed identifier (DOI, title) is re-verified against byte-identical evidence copies (re-hashed, re-scanned), the PRISMA-style flow counts are independently recomputed and compared with the run ledger, every exclusion must carry a reason code, and result.json is validated against the case contract (case_id match, every output_contract field non-empty and pointing at real files under /app/output, success only with empty uncertainty, partial only with honest non-empty uncertainty). Any unverifiable identifier is a FABRICATION_SUSPECT ERROR that flips the gate to FAIL; --fix-result repairs result.json into an honest partial state but never touches candidates. Ships with a deliberately simple stdlib-only baseline search (lite_search.py) so every run has a real, auditable trail. Use for 学术文献检索/literature-search cases where organizer-local snapshots are the only sources, the budget is tight, and independent verifiability (评审复核) decides the score.
---

# retrieval-run-warden — the run must prove itself

Philosophy: **the cheapest way to lose a retrieval case is to ship one phantom
DOI or one empty contract field.** Not a weak ranking, not a missed synonym —
a single identifier that exists in no source, or a `result.json` that claims
`success` while a contract field dangles. This skill is the warden of the run,
not a better search algorithm: whatever the retrieval produced, the warden
makes it *prove* itself. Every claim must exist in byte-identical evidence,
every count must recompute, the contract must validate, and `partial` means
honestly partial.

The agent contributes judgment (reading the case, running its own search,
deciding what the findings mean); the warden does everything mechanical
deterministically, offline, stdlib-only — and it never edits the run's
candidates, because repairing evidence would be laundering.

## Runtime contract

- Platform installs this skill at `/skills/weekly-skill` and runs fixed cases:
  input `/input/case.json` + `/input/task.md` (+ organizer-local snapshots),
  work under `/app/work`, deliverables under `/app/output`, including
  `result.json` with the original `case_id` and **every** field named by
  `output_contract`. No live remote coverage; budget ≈ 8–12 model requests.
- First action in any run: `ls -R /input` and read `case.json` — note
  `case_id`, every `output_contract` field name, and what snapshot material
  actually exists.
- Save a partial `result.json` before searching; let the warden tell you what
  is wrong; keep `status=partial` whenever anything material is missing.
- The run directory layout the warden audits (produce this even if you use
  your own search instead of `lite_search.py`):

  ```
  /app/work/run/
    candidates.json      # {"candidates": [{doi,title,evidence:{copy_name,
                         #   sha256_12,json_index},dedup_key,...}]}
    candidates.md        # human-readable, same claims
    run_log.jsonl        # one JSON per step; must contain a "prisma" step with
                         # counts {identified, after_dedup, included} and an
                         # "exclusions" step whose items carry reason codes
    evidence/            # byte-identical copies of every consulted snapshot,
                         # named <sha256_12>__<original-name>
  ```

## Procedure

1. **Secure a partial result immediately:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status partial \
       --uncertainty "run not started yet"
   ```

   (If the skill landed elsewhere, locate it with `ls /skills/*/scripts/`.)

2. **Run a retrieval that leaves an auditable trail.** Either the bundled
   honest baseline:

   ```
   python3 /skills/weekly-skill/scripts/lite_search.py \
       --case /input/case.json --input /input --work /app/work \
       --out /app/output
   ```

   or your own search — but then you must write the same run layout above
   (candidates with evidence pointers, run_log.jsonl with a `prisma` step and
   reason-coded exclusions, byte-identical evidence copies). A run without an
   evidence pool cannot be audited and will FAIL the warden. Never hand-edit
   a snapshot; doctored inputs defeat the evidence check.

3. **Audit the run:**

   ```
   python3 /skills/weekly-skill/scripts/warden.py \
       --case /input/case.json --run /app/work/run --out /app/output
   ```

   It prints a one-line JSON digest (`GATE`, per-gate PASS/FAIL, error and
   warning counts) and writes `/app/output/audit_report.md|json`. Exit 0 =
   PASS, exit 1 = FAIL. At this stage CONTRACT findings about empty fields
   are expected — result.json is not final yet.

4. **Fix exactly what the findings say.** Each finding names its gate, the
   offending identifier/field/count, and how to re-check it by hand.
   - `FABRICATION_SUSPECT` → the candidate is not in any evidence copy. Remove
     the claim by re-running retrieval correctly; **never** patch evidence or
     candidates to match.
   - `COUNT_MISMATCH` / `EXCLUSION_*` → the ledger does not recompute; fix the
     run, not the ledger.
   - `CONTRACT_*` → fill the named field with `--set`, fix `case_id`, or
     resolve the status/uncertainty contradiction.
   - `WARN` anomalies (zero-hit terms, empty snapshots, high dedup ratio,
     single-source pool) → copy them into `uncertainty`; they are honest
     coverage gaps, not failures.

5. **Finalize and validate:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status partial \
       --uncertainty "<every material gap, in words>"
   python3 /skills/weekly-skill/scripts/warden.py \
       --case /input/case.json --run /app/work/run --out /app/output
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --validate
   ```

   Use `--status success` only when the warden reports zero ERRORs **and**
   zero material gaps (success requires empty `uncertainty`). If the run is
   broken beyond repair, `warden.py --fix-result` rewrites result.json into an
   honest state — contract fields filled from existing artifacts, status
   downgraded to `partial` with the ERROR findings listed in `uncertainty` —
   without ever touching candidates or evidence. Re-audit afterwards; a
   fabrication finding survives the repair by design.

## What the warden guarantees (do not break these)

- **No fabrication ships:** every DOI and normalized title claimed by
  `candidates.json`, `candidates.md`, or `result.json` must literally appear
  in a re-hashed evidence copy, or the gate is FAIL with the identifier named.
- **No silent accounting:** identified / after-dedup / included are recomputed
  from the evidence bytes, not trusted from the log; every excluded record
  needs a reason code.
- **No empty promises:** the contract gate checks `case_id`, every
  `output_contract` field, file existence under `/app/output`, and the
  status ⇄ uncertainty consistency both ways.
- **The warden never edits candidates.** `--fix-result` touches only
  `result.json` (and stages byte-identical copies of run artifacts into the
  output dir). A FAIL report with findings is itself an honest deliverable —
  ship it rather than a laundered PASS.

## Exception handling

| Situation | Handling |
|-|-|
| No snapshots under /input at all | lite_search exits 2 with `ENGINE_STATUS=empty`; the warden reports `EVIDENCE_DIR_MISSING`/`CANDIDATES_MISSING`. State plainly that the case shipped no local corpus; deliver partial with that in `uncertainty`. |
| Agent used its own search tools | Fine — but save raw responses under `/app/work/corpus/`, pass `--corpus` to lite_search, or emit the same run layout yourself. No evidence copies → no audit → no PASS. |
| FABRICATION_SUSPECT on a record you are sure is real | The identifier is not byte-present in any evidence copy. Most often the snapshot was never copied into `evidence/`, or the DOI was normalized differently. Fix the run; do not edit evidence. |
| COUNT_MISMATCH after manual edits to candidates.json | Expected — the ledger no longer recomputes. Re-run retrieval instead of editing outputs. |
| GATE FAIL with no time to fix | Run `warden.py --fix-result`, re-audit, deliver. Status is `partial`, findings are listed in `uncertainty`, and the FAIL audit report is part of the deliverable. |
| result.json validation fails | Fix exactly the reported field with `--set`; never blank a contract field, never claim `success` with non-empty `uncertainty`. |

## Resources

- `scripts/lite_search.py` — honest baseline retrieval run (stdlib only,
  offline); writes the full auditable run layout.
- `scripts/warden.py` — the four-gate audit (ANTI-FABRICATION, FLOW,
  CONTRACT, ANOMALY) plus `--fix-result` repair.
- `scripts/make_result.py` — output_contract-driven result.json
  builder/validator.
- `references/methodology.md` — every gate check, severity policy, the
  run-directory layout contract, and known limits, so each verdict can be
  defended.
- `references/selfcheck.md` — pre-submission checklist.
- `examples/minimal_example.md` — two real local runs on a synthetic fixture:
  a clean PASS and a tampered FAIL with a phantom DOI (outputs marked as
  synthetic example, not a formal case result).
