---
name: quantity-audit
description: Recalculate every checkable published number from a paper's own formulas, symbols, values and units — with an exact SI dimensional engine, dimensionless-exponent checks, residuals against reported values and an honest per-claim audit ledger; use whenever a formula-reading task includes computable equations or reported numerical results that must be verified rather than trusted.
---

# quantity-audit: numerical recomputation audit (算得回 · 数值审计)

Core stance: **a reported number is a claim to be re-derived, not a fact to be
copied.** This skill's center of gravity is the physics of numbers: every
quantity carries a value, a unit and a source location; every formula is
evaluated in exact SI dimensions; every reported value is compared with the
independently recomputed one and the residual is published — whether it
matches or not.

This is not a transcription skill and not a prose-explainer. The deliverable
is an **audit ledger**: one row per checkable claim with LHS/RHS SI values,
dimension verdict, relative error vs the reported value, and a PASS/MISMATCH/
BLOCKED status. A claim whose inputs are absent is BLOCKED with named missing
objects — never filled with zeros, never reverse-engineered.

## Runtime contract

- Input: `/input/case.json` and `task.md`; materials under
  `case.json.artifacts`. Read actual files.
- Create `/app/work` immediately; write `/app/output/result.json` **early as
  an honest partial** containing the original `case_id` and every
  `output_contract` field; update it after each audit stage.
- Final `result.json` uses the contract's own field names, types and status
  enumeration. Status law: `success` only when every declared checkable claim
  was computed; `partial` when some claims are BLOCKED; `insufficient_evidence`
  when the materials carry no formula representation or no usable values
  (the missing-formula branch — report it, do not invent equations).
- Never present prepared answers: the ledger is produced by
  `scripts/recalc_audit.py` from a claims file written from the actual paper.

## Workflow

1. **Bootstrap.** `python3 scripts/case_bootstrap.py --input /input --work /app/work --out /app/output`
   creates the tree and the early partial `result.json`.
2. **Build the claim ledger.** Read the publisher XML / PDF text and write
   `/app/work/claims.json` following `references/claim_schema.md`: for each
   computable formula, the LaTeX, a binding of every symbol to
   `{value, unit, source}` (source = section/table/page where the value is
   stated), and the `reported` value with its source. Mark any symbol the
   paper does not give a value for as `{"unknown": true}` — do not guess.
3. **Run the audit.** `python3 scripts/recalc_audit.py --claims /app/work/claims.json --work /app/work --out /app/output`.
   The engine parses the LaTeX into an AST (`scripts/latex_ast.py`), converts
   every bound value to SI (`scripts/si_engine.py`), evaluates the RHS,
   checks dimension equality, enforces dimensionless arguments for
   `exp/sqrt-of-dimensional` misuse, and compares against the reported value
   in the reported unit. Intermediate SI values are printed so the run can be
   re-checked by hand.
4. **Interpret residuals.** A PASS means the recomputed value reproduces the
   reported one within the claim's tolerance (default 2% relative or the
   paper's own rounding). A MISMATCH with correct dimensions usually signals
   an arithmetic or rounding problem in the source (or in the extracted
   binding — re-check the source location). A DIM_MISMATCH signals a unit or
   structural error. Record all of it; do not downgrade a genuine mismatch to
   a pass.
5. **Finalize.** Copy the ledger summary into `result.json`: per-claim
   verdicts, named BLOCKED inputs, and the uncertainty section. Attach
   `audit_ledger.json` as an artifact.

## Exception handling

- LaTeX construct not supported by the parser: the claim is BLOCKED with the
  parser's error message; simplify the claim to a supported form and retry,
  or mark it UNPARSEABLE — never silently drop it.
- Unknown symbol value: BLOCKED listing the symbol and where its value was
  sought.
- Compound units with fractional group powers such as `(V cm^-1)^-1/2` are
  supported; unsupported unit spellings are BLOCKED with the spelling.
- Missing-formula branch (no formula artifacts at all): audit the explicitly
  stated metrics for consistency only, then report `insufficient_evidence`
  for formula-level verification.

## Minimal example (SYNTHETIC — not a platform case, not evidence)

`examples/run_synthetic_example.sh` audits two fabricated claims (an
Einstein-relation value and a Poole–Frenkel mobility, invented constants) and
one deliberately wrong counter-example claim, producing PASS, MISMATCH and
DIM_MISMATCH rows so the full verdict vocabulary is demonstrated. All numbers
are synthetic.

## Requirements and limitations

Python 3.9+ standard library only; no network, no third-party CAS. The LaTeX
parser covers the subset listed in `references/claim_schema.md` (fractions,
scripts, `\sqrt`, `\exp`, fences, Greek letters, implicit multiplication);
wider constructs must be simplified by hand. Dimensional analysis checks
consistency, not physical correctness of a model; a dimensionally-clean wrong
model still passes dimensions and must be caught by residuals or reading.
