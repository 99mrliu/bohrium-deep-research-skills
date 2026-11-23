# Minimal example (SYNTHETIC — 合成示例, not a formal test case)

Synthetic input only: a 3-page artificial paper PDF, synthetic
`case.json`/`target-fields.json` (6 fields). All outputs below are 示例
from the synthetic run.

## Commands and observed behaviour (示例)

```bash
python3 scripts/pipeline.py run --input-dir /input --work-dir /app/work \
    --output /app/output/result.json
# orient -> extract -> bank -> skeleton done, then:
# GATE: adjudicate pending — do field work, then:
#   pipeline.py mark adjudicate --work-dir /app/work

python3 scripts/pipeline.py status --work-dir /app/work
```

Observed synthetic status (示例):

```text
orient      done   ...  6 fields, pdfs=['synth_paper.pdf']
extract     done   ...  extract: 3 pages -> pages.txt
bank        done   ...  bank: 13 entries -> bank.jsonl
skeleton    done   ...  honest partial: 6 fields not_reported
adjudicate  PENDING
finalize    PENDING
```

The skeleton step already wrote a **valid honest partial** result.json
(every field `not_reported`, `status: partial`) — an abort at this point
still leaves a deliverable.

## Closing the gate and finalizing (示例)

After field adjudication (4 fields reported, 2 honestly `not_reported`
because the synthetic table cell says `n.d.` and the paper states
high-temperature behaviour is unreported):

```bash
python3 scripts/pipeline.py mark adjudicate --work-dir /app/work \
    --note "6/6 fields decided (4 reported, 2 not_reported)"
python3 scripts/pipeline.py run --input-dir /input --work-dir /app/work \
    --output /app/output/result.json
# finalize: OK status=partial fields=6 uncertainties=2
# pipeline: done (orient,extract,bank,skeleton,finalize)
```

The rerun skipped completed stages (idempotent) and finalize recomputed
the overall status from field-level outcomes: `partial`, because two
fields are genuinely not reported. `change_records` (9 lines from run.log)
were appended to the result.

## Negative check observed in the synthetic run (示例)

Two contract violations (a reported field without page, a scalar not
verbatim in its quote) fail finalize loudly:

```text
ERROR: capacity_composite_100cyc: reported without page
ERROR: retention_composite_100cyc: scalar not verbatim in quote
finalize: FAIL (2 errors)   exit=1
```
