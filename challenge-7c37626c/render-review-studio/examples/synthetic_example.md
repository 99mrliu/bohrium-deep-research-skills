# Minimal example (SYNTHETIC — interface demonstration, not a platform case)

## Input

`examples/fixture/input/case.json` declares a PDF artifact (written at
runtime — the bundle ships no binary), `examples/fixture/formulas.json`
carries two transcriptions plus a deliberately malformed third formula, and
`examples/fixture/variables.json` a three-row variable table.

## Invocation

```bash
bash examples/run_synthetic_example.sh
```

## What a passing run looks like

- `app/output/render/formula_eq1.png`, `formula_eq2.png`: strict mathtext
  renderings of the synthetic Einstein and Poole–Frenkel formulas.
- `render_report.json`: `eq3` listed under `unrenderable` with the mathtext
  engine's own error — reported, not dropped.
- `app/output/render/compare_eq1.png`, `compare_eq2.png`: side-by-side
  sheets, source page raster (left) vs rendered transcription (right).
- `app/output/render/variables_p1.png`: the variable table as an image.
- `app/output/review_report.md` + `result.json`: preview manifest with byte
  sizes; `unrenderable` names `eq3`; status `success` because every
  renderable preview exists and exceeds the byte floor (the malformed
  formula is a finding, not a missing artifact).

All materials, transcriptions and previews in this example are synthetic.
