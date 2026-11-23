# Minimal example (SYNTHETIC — interface demonstration, not a platform case)

## Input

Two fabricated cases sharing one contract (`case_id, status, answers,
evidence, uncertainty, artifacts`, with `field_types` and a status enum):

- `examples/fixture/input-xml/`: an xml_rich case with a fabricated
  publisher XML containing MathML.
- `examples/fixture/input-metrics/`: a metrics-only case (no formula
  representation, no recalculable data) — the missing-evidence branch.

## Invocation

```bash
bash examples/run_synthetic_example.sh
```

## What a passing run looks like

XML branch:

1. `triage_case.py` reports `branch: xml_rich` and banks the early partial
   `result.json` before anything else happens.
2. A deliberately defective interim result (contract field `answers` left
   null without a reason, status claimed `success`) **fails the linter**:
   `null-reason violation: field 'answers' is null but not named in
   uncertainty`.
3. `finalize_gate.py` downgrades the claimed `success` to `partial` and
   records the transition in `audit_trail.json`.
4. After the agent repairs the result, lint is CLEAN and the gate keeps the
   earned `success`.

Metrics branch: triage reports `metrics_only` with its limitations; the
interim result restates the one explicit metric with its condition and marks
formula-level tasks `insufficient_evidence` with the missing objects named;
lint is clean and the gate preserves `insufficient_evidence` — the honest
terminal state for a missing-evidence branch.

All materials and outputs of this example are synthetic.
