# Status state machine

```
                 triage (branch known)
                        |
                  status = partial  <---- any checkpoint rewrite
                        |
        +---------------+----------------+
        |                                |
   lint clean                      lint violations
        |                                |
 finalize_gate                     finalize_gate (fail-closed)
        |                                |
  success / partial /             partial (violations named in
  insufficient_evidence             uncertainty.gate_violations)
```

## Semantics

- `success` — every contract field non-null (or every null with a named
  reason) and all required analysis completed. Earned, not claimed.
- `partial` — some analysis incomplete, some inputs degraded, or gate
  violations exist. The result must identify its limits.
- `insufficient_evidence` — the materials cannot support the requested
  analysis (metrics-only branch, unreadable source). Name the missing
  objects; do not reverse-engineer or zero-fill.
- `failed` — the run itself broke (permission, crash). State the failure
  point and the manual handoff location.

## Audit trail

`finalize_gate.py` appends every finalize to
`/app/work/audit_trail.json` (`from`, `to`, violations, timestamp). The
trail is append-only; a status that moved is visible forever. Multiple
transitions in one run (e.g. after a repair) are expected and honest.
