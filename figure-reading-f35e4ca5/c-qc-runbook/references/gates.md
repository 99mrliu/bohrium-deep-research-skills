# The six gates and the budget clock

The runbook fits the harness budget (~900 s, 64 model calls). Each gate
has a time checkpoint; missing a checkpoint triggers the escalation
ladder, not silent overtime.

| Gate | Artifact (in /app/work) | Pass criteria (machine-checked) | Timebox |
|-|-|-|-|
| g0 | result.json skeleton | written by start_run.py at minute 0 | 0–30 s |
| g1 | inventory.json | every input file classified; contract fields extracted | ≤120 s |
| g2 | axis_card.json | ≥3 ticks/axis, monotonic px+values, declared type == tick geometry, plot_area well-formed, unit string sane | ≤300 s |
| g3 | element_ledger.json | every element typed/statused; read ⇒ locator; unreadable ⇒ reason; series read ≥ legend entries | ≤480 s |
| g4 | crosscheck.json | figure↔table pairs checked with ≥50% match, or written reason why nothing to check; caption semantics quoted | ≤660 s |
| g5 | result.json lint | units on every numeric value, case_id match, status honesty | ≤780 s |

Final freeze: T‑60 s — run finalize.py and stop editing. A submitted
honest partial beats an unsubmitted success.

## Escalation ladder (per element / per axis)

1. **auto** — read it with the disciplined method (zoom, axis card).
2. **assisted** — cross-check against tables/caption; if a value is
   confirmed by a table cell, quote the cell and move on.
3. **manual-best** — best-effort reading with an explicit error estimate.
4. **honest partial** — mark the element `unreadable` with the reason
   (occluded, cropped, overexposed, no scale) in the ledger and in
   result.uncertainty. NEVER fill a gap with a plausible-looking value.

When the gate-2 checkpoint is missed, go straight to the simplest sound
reading (fewer points, tick-anchored) instead of refining the method —
the gates protect completeness, not elegance.

## Why gates and not a pipeline script

The harness runs a generalist agent, not our code: what fails under time
pressure is PROCESS (skipped verification, silently swapped legends,
success claimed over null fields), not arithmetic. The gates convert the
process into machine-checked artifacts with exit codes, so a base agent
gets the same discipline every run, and the run_report.md proves it
happened.
