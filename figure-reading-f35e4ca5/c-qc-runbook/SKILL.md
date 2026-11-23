---
name: qc-gated-figure-reading
description: Run a scientific-figure reading as a budget-gated quality process — result-first skeleton at minute zero, then five machine-checked gates (input inventory, validated axis card with type-vs-geometry and unit checks, element coverage ledger with locators or explicit unreadable reasons, figure-vs-table/caption crosscheck, output lint enforcing units and honest status) that decide the final status from evidence and emit a run_report. Use when an agent must read charts under a tight time/call budget (科研图表解析质检, figure reading QC runbook, evidence-gated extraction) and the risk is process failure — skipped verification, silent gaps, success claimed over null fields.
---

# QC-gated figure reading

Core idea: **under a fixed budget, the difference between a 40-point and
a 90-point answer is process discipline, not cleverness.** This skill is
a run-management system: it writes a valid partial result.json at minute
zero, then forces every claim through five mechanical gates with exit
codes, so correctness checks happen while there is still time to fix
things — and the final status is computed *from the gate evidence*, not
claimed by the agent.

## Runtime contract

Read `/input/case.json` and `/input/task.md`; `output_contract` defines
the result fields. Work in `/app/work`; deliverables in `/app/output`,
including `result.json` (original `case_id` + every contract field +
honest status/status_reason/sources/uncertainty). Budget defaults to
900 s / 64 model calls; time checkpoints are set at gate 0 — see
`references/gates.md`. If paths differ outside the harness, pass real
paths via the CLI flags.

## Dependencies

Python 3, standard library only. No network, no pip, no image
libraries required (gates check process artifacts, not pixels).

## The runbook

0. **start_run.py** — minute zero:
   `python /skills/weekly-skill/scripts/start_run.py --case /input/case.json --task /input/task.md --work /app/work --out /app/output`
   Writes run_state.json (gates, checkpoints, budget clock) and a valid
   PARTIAL result.json with every contract field present-but-null.

1. **g1 inventory** — list and classify every file (figure/table/text),
   extract the contract fields:
   `python /skills/weekly-skill/scripts/gate.py --gate 1 --work /app/work --case /input/case.json`

2. **g2 axis card** — author `/app/work/axis_card.json` per panel per
   `references/axis_card.md` (verbatim label+unit, ≥3 ticks with pixel
   positions, declared type, plot-area box), then:
   `python /skills/weekly-skill/scripts/gate.py --gate 2 --work /app/work --case /input/case.json`
   Hard checks: tick geometry must agree with the declared type
   (log-on-linear and linear-on-log fail), tick pixels/values monotonic,
   unit string sane. **Do not read a single value until g2 passes.**

3. **g3 element ledger** — account for every element in
   `/app/work/element_ledger.json` per `references/element_ledger.md`
   (series, data points, error bars with their semantics, significance
   marks, scale bars, annotations; legend count vs series read), then:
   `python /skills/weekly-skill/scripts/gate.py --gate 3 --work /app/work --case /input/case.json`

4. **g4 crosscheck** — write `/app/work/crosscheck.json`: figure values
   vs the case's tables (checked/matched counts), caption semantics
   quoted verbatim (error bars, n, significance definition), or a
   written reason why nothing is checkable:
   `python /skills/weekly-skill/scripts/gate.py --gate 4 --work /app/work --case /input/case.json`

5. **read and fill** the contract fields in result.json (any extraction
   method you trust: manual zoom reading, table quotes, or other
   skills/tools — the gates are method-agnostic).

6. **g5 lint + finalize** (freeze at T‑60 s):
   `python /skills/weekly-skill/scripts/gate.py --gate 5 --work /app/work --out /app/output --case /input/case.json`
   `python /skills/weekly-skill/scripts/finalize.py --work /app/work --out /app/output --case /input/case.json`
   finalize.py computes the shipping status from the gates, stamps
   run_report.md (per-gate findings + timeline + budget usage), and
   refuses claims that the gates do not support.

## Failure catalogue

| Symptom | Diagnosis | Fix |
|-|-|-|
| g2 geometry fail | log axis declared linear or vice versa | re-read tick labels; ratio vs difference decides |
| g3 legend coverage fail | a legend series never read | re-read the legend; add the missing series entry |
| g3 locator fail | value marked read without a locator | add figure region / table cell / caption quote |
| g4 match-rate fail | most figure values don't match tables | calibration or legend mapping is wrong — go back to g2/g3, do not answer |
| g5 honesty fail | status success over null fields | finalize will downgrade; fill the fields or accept partial |
| checkpoint missed | out of budget | escalate per references/gates.md; ship the honest partial |

## Limits

- The gates verify the process, not the pixels: a perfectly gated run
  can still misread if the axis card itself was measured wrong — keep
  tick measurements zoomed and re-checked.
- For figures without numeric axes (micrographs), g2 is answered with a
  scale_bar-centric card: still tick-free, still gated for units and
  locators.
- Three repetitions per condition are expected to produce consistent
  gate outcomes; treat a gate that flips between runs as a signal to
  re-examine the artifact, not to rerun blindly.

See `examples/minimal_example.md` for a complete runnable synthetic
miniature (illustrative, not an official case result).
