# Examples — 合成示例 (synthetic example)

Everything in this directory is a **synthetic example, not an official case
result**. The paper PDF is fabricated (ASCII-only, stdlib PDF writer), the
plan is machine-generated from the extracted spans, and every output
artifact carries a synthetic marker (deck title prefix
`SYNTHETIC EXAMPLE — `, `result.json: {"synthetic_example": true}`).

## Files

- `make_fixture.py` — generates `work/input/paper.pdf` (3-page synthetic
  paper: title/abstract/intro, methods/results with
  `accuracy of 92.3% on the SynBench test set`, a vector figure with caption
  `Figure 1: Training loss over 50 epochs (synthetic).`, limitations),
  `work/input/case.json` (case_id `synthetic-demo-001` + six-field
  output_contract) and `work/input/task.md`. With `--emit-plan` (run after
  ingest + figure zoning) it writes `work/work/plan.json` whose bullet
  quotes REALLY verify against `spans.jsonl`.
- `run_example.sh` — full chain: fixture → pdf_ingest → figure_zones →
  emit-plan → early partial result.json → span_bind → build_deck → final
  result.json → artifact listing. `set -euo pipefail`.
- `expected_output.md` — expected artifacts, what each proves, and the
  deliberately-failing binding variant.

## Run

```bash
cd examples && bash run_example.sh
```

Requires `pdftotext` + `pdftoppm` on PATH (poppler). `soffice` is optional:
without it, `build_deck.py` skips PDF export/previews gracefully and records
the miss in `build_manifest.json` and `result.json` exceptions.

Outputs land in `examples/work/` (git-ignorable): `work/input/` (fixture),
`work/work/` (intermediates: spans.jsonl, ingest_report.json, figures.json,
bindings.json, plan.json, page renders, figure crops), `work/app-output/`
(presentation.pptx, result.json).
