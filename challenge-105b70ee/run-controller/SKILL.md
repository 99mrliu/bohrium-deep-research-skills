---
name: run-controller
description: >-
  Process-quality-control skill for paper field extraction under tight
  budgets (64 model requests, 900 s, 3 repetitions per case). A staged
  pipeline controller runs the deterministic steps (orient, extract, bank,
  skeleton, finalize) with checkpoints, per-stage timing and a run log, so
  the run is resumable, idempotent and always leaves a valid honest-partial
  result.json on disk; model budget is spent only inside the adjudicate
  gate between skeleton and finalize, tracked in a budget ledger. The
  finalizer recomputes an honest overall status from field-level outcomes
  and appends change records. Use when /input provides case.json,
  target-fields.json and a paper PDF and /app/output/result.json must be
  reproducible and failure-honest (concrete-reading-v2). 过程质量控制：
  分段检查点、预算台账、诚实部分结果、可复跑。
---

# Run Controller — 分段检查点 + 预算台账 + 诚实部分结果

**Core bet.** Under a 64-request / 900 s budget with three repetitions per
case, the biggest risks are process risks: running out of budget halfway,
losing work on interruption, inconsistent reruns, and a final status that
overclaims. This skill makes the **run itself** controlled: deterministic
stages with checkpoints, a valid result.json on disk from minute one, a
budget ledger for model requests, and a finalizer that computes the
overall status from field-level truth — never from optimism.

## When to use

- `/input/case.json` + `/input/target-fields.json` + paper PDF(s);
  `/app/output/result.json` must echo `case_id` and carry `status`,
  `result.field_results`, `claims`, `uncertainties`.

## The stage machine (paths relative to this SKILL.md)

```bash
python3 scripts/pipeline.py run --input-dir /input --work-dir /app/work \
    --output /app/output/result.json            # runs pending stages in order
python3 scripts/pipeline.py status --work-dir /app/work
```

| stage | who | what | checkpoint |
|-|-|-|-|
| `orient` | script | validates inputs exist, reads case_id + field list | `state/orient.json` |
| `extract` | script | PDF → `work/pages.txt` (pdftotext, pypdf, or `--text-file` after OCR) | `state/extract.json` |
| `bank` | script | harvests quantified/cued sentences → `work/bank.jsonl` | `state/bank.json` |
| `skeleton` | script | writes **valid honest-partial** result.json (all fields `not_reported`) | `state/skeleton.json` |
| `adjudicate` | **you** | field-by-field semantic work; then mark the gate | `state/adjudicate.json` |
| `finalize` | script | contract check, honest overall status, change records | `state/finalize.json` |

Stages are idempotent: rerunning `pipeline.py run` skips completed stages
(`--force` redoes one). Every stage appends to `work/run.log` with
timestamps; `status` shows what is done, pending, or stale.

## The adjudicate gate (where the budget goes)

After `skeleton`, spend model requests here only:

1. `grep -n "keyword\|unit\|中文词" /app/work/bank.jsonl` per field; read
   the sentence context in `work/pages.txt`.
2. Edit `/app/output/result.json` in place: for each `field_id` set
   `status` ∈ `reported|not_reported|source_conflict|extraction_failed`
   with `scalar/units/statistic/condition/comparator/quote/page/notes`.
   Rules: scalar verbatim inside quote; units as printed; condition
   mandatory for numeric values; absent ≠ zero (`not_reported` + searched
   terms in notes); `n.d.` cells → `not_reported` quoting the cell.
3. Record each model request in `work/budget.md` (one line: request #,
   purpose, fields touched). Stop field work when ≤6 requests remain.
4. Close the gate: `python3 scripts/pipeline.py mark adjudicate
   --work-dir /app/work --note "6/6 fields decided"`.

## Budget ledger rules (64 requests / 900 s)

- Steps outside the gate are free (scripts). Reserve: 1 orient-read + ≤58
  adjudicate + ≥3 finalize/claims + 2 slack.
- Hardest fields first (cross-page tables, ranges, `n.d.`, conflicts).
- If the ledger hits the reserve with fields undecided: leave them
  `not_reported` (the skeleton default) and say so in `uncertainties` —
  that is an honest partial, not a failure.
- Interruption-safe: any abort after `skeleton` leaves a valid
  result.json; rerunning continues from the last checkpoint.

## Finalize (0 requests)

```bash
python3 scripts/pipeline.py run --input-dir /input --work-dir /app/work \
    --output /app/output/result.json   # runs finalize once gate is marked
```

`finalize.py` verifies: `case_id` echoed; all `output_contract` keys;
every field decided exactly once with schema-consistent records; claims
have `kind` + located verbatim `evidence`. It then **recomputes** the
overall status: `answered` only when every field is `reported`;
`insufficient_evidence` when nothing was reportable; `partial` otherwise;
`input_error` when `orient` flagged unusable input. It appends
`change_records` (stage timeline from `run.log`) and mirrors non-reported
fields into `uncertainties`. Exit 1 on contract violations — fix and
rerun; the gate stays marked.

## Failure taxonomy (references/run-contract.md)

scanned PDF → OCR via `environment/resources.yaml` tool, `--text-file`;
no extractor → same fallback, else `input_error`; garbled table cell →
`extraction_failed` with location; request/time budget exhausted → honest
partial with undecided fields listed. Consistency across the platform's
three repetitions comes from the checkpoints: same input → same stages →
same artifacts.
