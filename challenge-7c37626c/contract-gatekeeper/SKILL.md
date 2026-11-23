---
name: contract-gatekeeper
description: Runtime-contract quality control for case runs — input triage that writes an early honest-partial result.json before any analysis, a fail-closed linter that validates the final result against the case's own output_contract, a null-reason rule, an audit trail, and first-class handling of missing-evidence branches; use whenever a run must survive interruption, report partial results honestly, and deliver exactly the schema the case demands.
---

# contract-gatekeeper: process quality control (过程质量控制)

Core stance: **the contract is the deliverable.** Whatever analysis a case
asks for, the run is a quality-controlled process: classify the input first,
bank an honest partial result before spending budget, checkpoint after every
stage, and let a fail-closed gate — not optimism — decide the final status.
This skill does not parse formulas; it guarantees that whatever parsing
happened is reported in exactly the schema the case declares, with missing
evidence named instead of silently dropped. C02-type branches (no formula
representation, no recalculable data) are a first-class outcome, not an
error.

## Runtime contract

- Input: `/input/case.json` and `task.md`; materials under
  `case.json.artifacts`. Read the actual files.
- Work under `/app/work`; final results under `/app/output`, including
  `result.json` with the original `case_id` and **every field the case's
  `output_contract` requires**, using the contract's names, types and status
  enumeration.
- Budget discipline (64 model requests / 900 s): `workplan.py` lays out a
  phase plan with checkpoints; every checkpoint rewrites `result.json` so an
  interrupted run still yields a valid, honest partial.
- A `partial` result must identify its limits; an `insufficient_evidence`
  result must name the missing objects. Nulls in contract fields require a
  named reason in `uncertainty` (the null-reason rule).

## Workflow

1. **Triage first.** `python3 scripts/triage_case.py --input /input --work /app/work --out /app/output`
   scans `/input`, classifies the branch (`xml_rich` / `formula_subset_only`
   / `pdf_only` / `metrics_only`), derives a capability matrix (what the
   case can support: transcription, symbol grounding, derivation mapping,
   numeric verification), and writes the **early partial** `result.json`
   plus `triage.json`. Nothing is analyzed before the partial is banked.
2. **Plan.** `python3 scripts/workplan.py --work /app/work` writes
   `plan.md`: phases with checkpoints matched to the triaged branch, so
   time and requests are budgeted against what the input actually supports.
3. **Analyze** (the agent's work, possibly with other skills), updating
   `result.json` at each checkpoint.
4. **Lint.** `python3 scripts/contract_lint.py --case /input/case.json --out /app/output`
   validates the interim result against the contract: required fields
   present, types match `field_types`, status in the enum, `case_id` exact,
   and no unexplained nulls in contract fields (each null must be named in
   `uncertainty`). Violations are listed verbatim in `lint_report.json`.
5. **Finalize.** `python3 scripts/finalize_gate.py --case /input/case.json --work /app/work --out /app/output`
   re-runs the lint, appends the status transition to `audit_trail.json`,
   and enforces the gate: any violation downgrades a claimed `success` to
   `partial` with the violations as the reason; a clean result keeps its
   earned status; the missing-evidence branch keeps
   `insufficient_evidence` with its named gaps.

## The null-reason rule

A contract field may be null only if `uncertainty` names the field and why
it is null. The linter implements this mechanically; the agent supplies the
honesty. An unexplained null is a defect the gate will not ship as success.

## Exception handling

- `case.json` missing or unreadable: triage reports `contract_unknown`,
  still banks a minimal `result.json` marked `partial`, and the reason is
  recorded. Never invent a schema.
- No formula-bearing artifact (metrics/prose only): branch `metrics_only`;
  the plan restricts itself to explicit-metric consistency checks, and the
  final status for formula-level tasks is `insufficient_evidence` with the
  missing objects named. Do not reverse-engineer formulas, do not fill
  unknowns with zero.
- Lint failure at finalize: degrade, name violations, ship — a flawed honest
  result beats a clean-looking false one.
- Interruption mid-run: the last checkpoint's `result.json` is the
  deliverable; the audit trail shows how far the run got.

## Minimal example (SYNTHETIC — not a platform case, not evidence)

`examples/run_synthetic_example.sh` runs the full QC loop on a fabricated
case: triage, plan, then a deliberately defective interim result (a contract
field left null without a reason) that the linter catches and the gate
downgrades, followed by the corrected result passing the gate. It then runs
the same loop on a metrics-only input and shows the
`insufficient_evidence` outcome. All materials are synthetic.

## Requirements and limitations

Python 3.9+ standard library only. The linter checks schema compliance and
the null-reason rule; it cannot judge whether a non-null answer is *right* —
that judgment belongs to the analysis skills and the reading agent. The
audit trail records status transitions, not model calls.
