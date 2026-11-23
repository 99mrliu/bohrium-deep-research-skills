# Minimal example (SYNTHETIC — interface demonstration, not a platform case)

## Input

`examples/fixture/input/case.json` is a fabricated case whose contract asks
for `case_id, status, answers, evidence, uncertainty, artifacts`.
`examples/fixture/claims.json` is the claim ledger an agent would write after
reading a fabricated paper: two genuine claims (Einstein relation `D = μ k_B
T / q` at `T = 300 K`, and the Poole–Frenkel mobility `μ(E) = μ_0 exp(β√E)`
at `E = 10^4 V/cm`) plus two deliberately wrong counter-example claims (a
value off by two decades, and a wrong unit exponent).

## Invocation

```bash
bash examples/run_synthetic_example.sh
```

## What a passing run looks like

The audit engine recomputes every claim in exact SI:

- `eq1-einstein-D`: `PASS` — recomputed `1.034e-5 cm^2 s^-1` vs reported
  `1.03e-5`, relative error below tolerance. Intermediate: `μ k_B T/q =
  1.034e-9 m^2/s`.
- `eq2-poole-frenkel-mu`: `PASS` — `β√E = 0.2` is checked **dimensionless**
  before `exp` is applied (this is the unit-error class the engine exists
  to catch).
- `counterexample-wrong-D`: `MISMATCH`, flagged with an
  `order_of_magnitude_shift` of ~2.00 decades — a unit-prefix or exponent slip.
- `counterexample-dim-err`: `DIM_MISMATCH` — the reported unit carries `L^1`
  where the formula yields `L^2`.

`result.json` ends with `status: success` (all claims were computed and
disagreements are recorded as ledger rows, not hidden) and points to
`audit_ledger.json` under the work directory.

All numbers, papers and outputs in this example are synthetic.
