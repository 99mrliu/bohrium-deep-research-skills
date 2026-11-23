# Run contract — checkpoints, budget, failure taxonomy, rerun rules

## Checkpoint protocol

- `state/<stage>.json` is written only when a stage **succeeds**; a failed
  stage leaves no checkpoint, so `pipeline.py run` retries it on rerun.
- `run.log` appends one line per completed stage and every failure, with
  wall-clock timestamps — it is the change record of the run.
- The `skeleton` checkpoint creates the first valid result.json. From that
  moment any abort (budget, timeout, crash) still leaves a deliverable:
  a complete field list with conservative `not_reported` statuses.

## Budget ledger (64 model requests / 900 s / 16384 tokens per response)

- Allocate outside the gate: 1 request to read inputs; inside the
  adjudicate gate: ≤58; finalize/claims: ≥3; slack: 2.
- `work/budget.md`, one line per model request:
  `#7 grep+read candidates for ice_first_cycle; bank W0017 accepted`.
- Track wall time in your head against 900 s: after extract+bank the
  scripts report their own duration in `state/*.json`; keep ≥120 s for
  finalize and a safety save.

## Failure taxonomy → recovery

| failure | detection | recovery |
|-|-|-|
| scanned PDF | extract exit 3, page yield ~0 | OCR via environment tool (`environment/resources.yaml`); `pipeline.py run --stage extract --text-file FILE`; note OCR fragility in uncertainties |
| no extractor | extract exit 4 | same fallback; if impossible → mark orient with note, status `input_error` |
| garbled table cell | bank quote not readable on spot-check | field → `extraction_failed` with page/cell location for a human |
| request budget exhausted | budget.md reserve hit | leave undecided fields `not_reported`, close gate with note, finalize honestly (`partial`) |
| time budget exhausted | >750 s elapsed | save result.json as-is (valid partial), skip claims, finalize |
| service failure | platform pauses separately | checkpoints make the resumed run cheap |

## Rerun rules (three repetitions per case)

Deterministic stages are a pure function of the input files: same input →
same `pages.txt`/`bank.jsonl`, so repetition drift comes only from the
adjudicate gate. To keep repetitions comparable:

- never edit `pages.txt`/`bank.jsonl` by hand;
- field edits go only into `result.json`, one field at a time;
- every edit carries `notes` (why accepted/rejected, searched terms);
- finalize after every batch of edits, not only at the end — each finalize
  refreshes status and uncertainties so the on-disk file is always honest.

## Status semantics (computed by finalize.py, never by hand)

- `answered`: every requested field `reported` (and claims verified).
- `partial`: mixed outcomes, or skeleton-defaults remain.
- `insufficient_evidence`: nothing was reportable after adjudication.
- `input_error`: input unusable (no readable paper / no fields).
