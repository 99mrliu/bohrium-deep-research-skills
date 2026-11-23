# Run record — synthetic example (DEMONSTRATION ONLY)

This record documents how the files in `examples/synthetic-output/` were
produced and verified. The input is the **synthetic, clearly marked** case
`examples/synthetic-case.json`; it is an interface demonstration, not an
official case result.

## 1. Commands

```bash
# main run (any working directory; paths shown relative to repo root)
python3 scripts/identity_resolver.py \
  --case examples/synthetic-case.json \
  --task examples/synthetic-task.md \
  --work <workdir> --out examples/synthetic-output

# full self-check (runs the pipeline twice into temp dirs, compares bytes,
# asserts 30+ expectations, tests CSV ingestion and invalid inputs)
python3 scripts/selfcheck.py

# regenerate the shipped outputs deterministically
python3 scripts/selfcheck.py --refresh-examples
```

## 2. Verification results (last local run)

- `python3 scripts/selfcheck.py` -> **SELF-CHECK PASSED (all checks)**:
  41/41, including:
  - determinism: two consecutive runs produce byte-identical output files;
  - alias merge: `TiO2` ≡ `titanium dioxide (rutile)` ≡ `titania`;
    `3000 meV` ≡ `3.0 eV` inside one study/locator/run;
  - no wrong merges: rutile ≠ anatase ≠ brookite, N-doped ≠ undoped,
    Na2SO4 ≠ Na2SO4·10H2O, 300 K ≠ 350 K ≠ unspecified context,
    source A ≠ source B (cross-source equal value reported as
    `not_duplicate` D-006, never merged);
  - repeated extraction (r0001/r0002, r0012/r0013) merged as
    `exact_duplicate`; independent replicate `run-2` kept as a distinct
    cluster with its own `experiment_id`;
  - conflict 3.05 eV vs 3.0 eV (same identity, same locator, same run) kept
    in separate clusters, values never averaged, queued for review;
  - unknown unit `Eg units` and missing unit flagged, normalized values stay
    null; `not reported` stays null; `2.3-2.5` kept as interval;
    25 eV Si band gap flagged out-of-range but not modified;
  - contract fields filled where semantics are unambiguous;
    `custom_unmapped_note` stays null and is listed in `unresolved`;
  - invalid inputs (malformed JSON, missing file) exit with code 2 and write
    an honest `input_error` partial `result.json`.

## 3. Observed output summary (this example)

- 19 input records -> 16 output rows; 3 rows merged as duplicates
  (`exact_duplicate` x2 clusters, `likely_duplicate` into the 3-member
  cluster cl-0001).
- Candidate states: exact_duplicate=2, likely_duplicate=2, conflict=3,
  not_duplicate=8 (4 independent-replicate D-005 + 4 cross-source D-006),
  review-state pairs=0 (review queue is driven by conflicts and anomalies).
- Review queue: 7 items (3 conflict pairs + unknown/missing unit, missing
  value, out-of-range); 8 anomalies total (plus info-level lexicon_miss and
  range notes).
- Change log: 40 rule-coded changes covering alias canonicalization (N-003),
  phase/dopant splits (N-004/N-005), missing-token nulling (V-003), range
  parsing (V-002), unit conversions with formulas (U-002), representative
  selection (D-008), duplicate merges (D-001/D-002) and explicit conflict
  retention (D-009).

## 4. Inspection notes

- Every output value in `cleaned_records.csv/json` traces to one real member
  row (`record_id`, `members[]` lineage, source DOI + locator).
- No timestamps or machine-specific paths appear in any output; rerunning is
  byte-identical, which is itself part of the self-check.
