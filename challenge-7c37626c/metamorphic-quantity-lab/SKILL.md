---
name: metamorphic-quantity-lab
description: Falsify numerical quantity claims with sourced inputs, independent invariants, unit/scale metamorphic tests, limiting cases, uncertainty intervals, and isolated fault-injection diagnostics.
---

# Metamorphic Quantity Lab

Use this skill when a task asks whether a reported numerical quantity is reproducible, especially C01/C03-style source claims with values or MathML, or C02-style claims whose raw values/formulas may be absent. Do **not** reduce verification to evaluating the claimed right-hand side once.

## Non-negotiable rules

1. The agent must obtain every empirical numeric value from an identified source and record `source.locator`. MathML may encode a sourced value, but the tool never searches for or invents source values.
2. Missing raw values, an unavailable formula, missing units, or absent source locators produce `partial`/`insufficient_evidence`. Never insert zero, one, or a plausible surrogate.
3. Supply independently authored metamorphic properties in JSON. The tool executes only supplied properties; it does not derive properties from the claim. An invariant is independent only when it is not algebraically derived from the claimed result.
4. Equality within tolerance is not validation of the model, assumptions, physical law, or source. It is only a bounded numerical compatibility check.
5. A diagnosis from `fault_injections` stays in `diagnostic_fault_injection_verdict`; it never changes `source_claim_verdict`.
6. With no usable independently authored property, the overall run remains partial even if the reported interval is compatible.

## Workflow

1. Read `/input/task.md` and `/input/case.json`. Extract the dynamic output contract before calculating.
2. Populate sourced quantities, reported claims (including intervals and explicit tolerances), independently authored property specs, and optional diagnostic mutations as described in `references/INPUT_SCHEMA.md`.
3. Run:

   ```bash
   python3 scripts/verify_case.py \
     --case /input/case.json --task /input/task.md \
     --work-dir /app/work --output /app/output/result.json
   ```

   This writes an honest partial result before evaluation, then `/app/work/analysis.json` and `/app/work/report.md`. Monotonic sweeps also produce CSV and, when matplotlib is available, PNG artifacts.
4. Read the residuals, converted intermediate inputs, property outcomes, and mutation outcomes. Investigate discrepancies rather than tuning tolerances to obtain agreement.
5. Write agent-authored answers to a UTF-8 JSON file and finalize:

   ```bash
   python3 scripts/finalize_result.py \
     --case /input/case.json --task /input/task.md \
     --analysis /app/work/analysis.json \
     --answers /app/work/answers.json \
     --artifacts /app/work/analysis.json /app/work/report.md \
     --output /app/output/result.json
   ```

   Add sweep artifacts when useful. The finalizer enforces `case_id`, all dynamic contract fields, `required_fields`, `field_types`, nested required properties, and `status_enum`. It will not turn incomplete evidence into a complete result.

See `references/METAMORPHIC_AUTHORING.md` for property design and `references/RESULT_CONTRACT.md` for finalization. `examples/run_synthetic_example.sh` is a complete invented-formula demonstration; all identifiers in it are explicitly synthetic.
