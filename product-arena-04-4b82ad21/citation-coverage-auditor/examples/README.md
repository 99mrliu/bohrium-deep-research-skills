# Examples — citation-coverage-auditor

> **SYNTHETIC EXAMPLE — interface demonstration only.** The case under
> `synthetic-case/` is entirely invented: the manuscript ("PermaLig"), all
> six references, their authors, journals, years, DOIs and abstracts are
> fabricated. Nothing here is a real scientific fact, and none of it is one
> of the organizers' fixed cases. Do not submit these precomputed answers
> (or derivatives) for any real case.

## What the example shows

An end-to-end audit of a well-formed synthetic introduction:

1. `bib_parse.py` normalizes `synthetic-case/material/references.json` into
   `bib.json` and cross-checks it against the human-readable
   `material/references.md` (6 entries, 0 disagreements).
2. `numbering_check.py` verifies that the filled draft
   `synthetic-case/filled/introduction.md` numbers its 6 Vancouver markers
   `[1]`–`[6]` strictly by first appearance (no `--fix`).
3. `coverage_ledger.py` builds the coverage ledger against
   `synthetic-case/case.json`: 6 distinct citations vs the required minimum
   of 4; all 3 mandated topics covered; top-2 closest works (by overlap
   with the problem statement) cited; recency and decorative-citation lint
   clean.
4. `claimcite_check.py` verifies claim-to-citation correspondence between
   the draft and `synthetic-case/filled/claims.json` (5 claim objects in
   the `facts_and_sources` shape): no orphan citations, no disconnected
   claim records.

All four steps exit `0` on this well-formed demo.

## Exact commands

From this directory (`examples/`):

```bash
bash run_example.sh
```

which is equivalent to:

```bash
SKILL_DIR=..
CASE_DIR=synthetic-case
OUT=sample-output
mkdir -p "$OUT"

python3 "$SKILL_DIR/scripts/bib_parse.py" \
  --json "$CASE_DIR/material/references.json" \
  --md   "$CASE_DIR/material/references.md" \
  --out-dir "$OUT"

python3 "$SKILL_DIR/scripts/numbering_check.py" \
  --bib   "$OUT/bib.json" \
  --draft "$CASE_DIR/filled/introduction.md" \
  --out   "$OUT/numbering_report.json"

python3 "$SKILL_DIR/scripts/coverage_ledger.py" \
  --case  "$CASE_DIR/case.json" \
  --bib   "$OUT/bib.json" \
  --draft "$CASE_DIR/filled/introduction.md" \
  --out-dir "$OUT"

python3 "$SKILL_DIR/scripts/claimcite_check.py" \
  --draft  "$CASE_DIR/filled/introduction.md" \
  --claims "$CASE_DIR/filled/claims.json" \
  --bib    "$OUT/bib.json" \
  --out    "$OUT/claimcite_report.json"
```

## What `sample-output/` contains

These are **real outputs produced by actually running `run_example.sh`**
(exit code 0 overall):

| file | produced by | contents |
|---|---|---|
| `bib.json` | `bib_parse.py` | 6 normalized entries with keys, metadata and `evidence_level` |
| `xcheck_report.json` / `xcheck_report.md` | `bib_parse.py` | field-by-field cross-check of json vs md representations (0 disagreements) |
| `numbering_report.json` | `numbering_check.py` | 6 markers, first-appearance order 1..6, no violations, status `pass` |
| `coverage_ledger.json` / `coverage_ledger.md` | `coverage_ledger.py` | coverage checklist table, topic mappings, closest-work ranking, recency histogram |
| `claimcite_report.json` | `claimcite_check.py` | 5 claims (all prior-work), 6 markers, 0 failures, status `pass` |

To see the failure modes, copy the draft to a scratch directory, swap two
citation numbers, and re-run `numbering_check.py` (it exits 1); then run it
with `--fix` and confirm the renumbered draft passes a re-check. See
`references/vancouver_rules.md` §4 for the full procedure.
