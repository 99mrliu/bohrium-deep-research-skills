# Pre-submission selfcheck — incremental-import-reconciler

Run through this list before finalizing any case. Every item is verifiable
from files, not memory.

## Contract

- [ ] `result.json` exists under `/app/output` and passes
      `make_result.py --validate` with zero errors.
- [ ] `case_id` in `result.json` equals the one in `/input/case.json`.
- [ ] Every field named by `output_contract` is present and points to a real
      file (`import_manifest.json`, `updated_state.json`,
      `reconciliation_report.md`, `change_records.jsonl`, evidence index).
- [ ] `status=success` only when `uncertainty` is empty; otherwise `partial`
      with concrete notes (queued conflicts, suspects, initial mode, empty
      pool, corrupt state).

## State integrity

- [ ] The digest's `mode` is `incremental` and `state_origin` points at the
      organizer's actual state — or, if `initial`, `uncertainty` says plainly
      that no prior state was found.
- [ ] No state file was deleted, renamed or bypassed to get the run through;
      a corrupt state means partial delivery with the defect ledgered, never
      a forced fresh import.
- [ ] `updated_state.json` contains the prior entries plus exactly the
      manifest's adds/updates — nothing else.

## Reconciliation correctness

- [ ] Counts in `import_manifest.json`, `reconciliation_report.md` and the
      stdout digest agree with each other.
- [ ] Every UPDATED decision has a non-empty field-level diff, and each diff
      was eyeballed as a plausible upstream correction (not a schema artifact).
- [ ] Every CONFLICT is listed in the report with both records, was resolved
      by a documented human decision or is openly carried in `uncertainty` —
      none was silently merged or dropped.
- [ ] Every SUSPECT exclusion has a reason code you can defend.
- [ ] `change_records.jsonl` has exactly one line per applied add/update, each
      with provenance `{file, json_index}`.

## Idempotency

- [ ] The run was made with `--verify-idempotent` and the exact line
      `IDEMPOTENT: second pass = 0 adds, 0 updates` appeared in the output of
      this session (a real second execution, not a claim in prose).
- [ ] No artifact under `/app/output` was hand-edited after the engine run;
      every change came from a re-run.

## Honesty

- [ ] No live-coverage or "latest publication" claim: the pool is exactly the
      local snapshots, and that bound is stated when material.
- [ ] Missing metadata is `null` in JSON, "—"/explicit in Markdown; nothing
      was guessed.
- [ ] `evidence/evidence_index.json` covers the case file, the state file and
      every pool file that was consulted.
