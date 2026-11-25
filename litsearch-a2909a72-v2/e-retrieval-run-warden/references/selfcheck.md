# Pre-submission checklist — retrieval-run-warden

Run through this in order before delivering `/app/output/result.json`.
Every item maps to something a reviewer can independently re-check.

## Identity and contract

- [ ] `result.json` exists at `/app/output/result.json` and parses as JSON.
- [ ] `case_id` in `result.json` is byte-identical to `/input/case.json`.
- [ ] **Every** field named by `output_contract` is present, non-empty, and
      points to an existing file under `/app/output` (no dangling paths, no
      paths into `/app/work` or `/input`).
- [ ] `status` is one of `success` / `partial` / `failed`.
- [ ] `status=success` ⇔ `uncertainty` is empty; `status=partial` ⇒
      `uncertainty` says in words what is missing.

## Fabrication sweep

- [ ] The final warden audit was run **after** the last edit to any artifact,
      and printed `"GATE": "PASS"` (exit 0) — or, if FAIL, the FAIL report is
      shipped deliberately with findings listed in `uncertainty`.
- [ ] No `FABRICATION_SUSPECT` findings remain: every DOI/title claimed in
      `candidates.json`, `candidates.md`, or `result.json` greps successfully
      against `<run>/evidence/`.
- [ ] No hand edits to `candidates.*`, `run_log.jsonl`, or `evidence/` after
      the run that produced them. If anything was edited, the run was re-done
      and re-audited.
- [ ] Evidence copies re-hash to their filename prefixes
      (`shasum -a 256 <run>/evidence/*` vs names).

## Flow accounting

- [ ] `run_log.jsonl` contains a `prisma` step; its `identified` /
      `after_dedup` / `included` counts match an independent recount from the
      evidence copies.
- [ ] Every record that was identified but not shipped appears in the
      `exclusions` ledger with a reason code (`DUPLICATE_OF`,
      `NO_TERM_MATCH`, …).

## Honest gaps

- [ ] Every WARN anomaly (`ZERO_HIT_TERMS`, `EMPTY_SNAPSHOT`,
      `HIGH_DEDUP_RATIO`, `SINGLE_SOURCE_POOL`) is either resolved or copied
      into `uncertainty` in plain language.
- [ ] No coverage gap is hidden by deleting terms, loosening matching, or
      trimming the candidate list by hand.

## Final validation

- [ ] `python3 /skills/weekly-skill/scripts/make_result.py --case
      /input/case.json --out /app/output/result.json --validate` prints
      `VALIDATE OK` (exit 0).
- [ ] `audit_report.md` is readable top to bottom: a reviewer could re-check
      every finding by hand using only the report and the evidence pool.
- [ ] If the gate is FAIL: `warden.py --fix-result` was run, the re-audit
      still fails only on the unfixable findings, and those findings are
      listed in `uncertainty` — the honest FAIL was shipped, not a laundered
      PASS.
