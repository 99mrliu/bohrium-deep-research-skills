# Minimal example (SYNTHETIC — interface demonstration, not a platform case)

## Input

`examples/fixture/input/` contains a fabricated JATS-like
`publisher-source.xml` (Einstein relation `D = μ k_B T / q` with invented
constants) and a derived `source-formulas.xml` subset, plus a `case.json`
whose `output_contract` requires `case_id, status, answers, evidence,
uncertainty, artifacts` with the standard status enum.

## Invocation

```bash
bash examples/run_synthetic_example.sh
```

The script mirrors the runtime contract on a scratch root
(`/tmp/mml-forensics-example`): `input/` ↔ `/input`, `app/work` ↔ `/app/work`,
`app/output` ↔ `/app/output`, and runs
`case_bootstrap.py → forensic_scan.py → crosscheck_layers.py → merge_result.py`.

## What a passing run looks like

- `forensic_report.json`: both XMLs well-formed; SHA-256 per file; structure
  stats showing `mfrac`/`msub` present; subset node `eq1` matches the source
  node `identical` by id and structural signature.
- `crosscheck.json`: `eq1` reports `structure_agreement: identical` between
  MathML and alttext; PDF layer `skipped` (no PDF in this example fixture).
- `result.json`: `status: success`, `verified_formulas: ["eq1"]`, evidence
  entries carrying per-file hashes, and an `uncertainty` section recording
  the skipped PDF layer as a note (not a violation).

## What a degraded run looks like (try it)

Introduce a divergence, e.g. delete the `mfrac` wrapper from
`source-formulas.xml` (flattening), or change the alttext to
`D = μ k_B T q`. The merge step reports `partial` and names the divergent
formula and the differing features instead of silently succeeding. Delete
`source-formulas.xml` entirely and the verdict becomes
`insufficient_evidence` for formula-level checks.

All materials, constants and outputs of this example are synthetic.
