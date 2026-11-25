# Synthetic end-to-end example (合成示例)

**Everything here is synthetic.** `make_fixture.py` fabricates a 2-page
English paper PDF about the fictional "SynNet" study (title says SYNTHETIC);
every number in it is invented. The example exists to prove the pipeline runs
end-to-end and that the number audit fails closed on hallucinated numbers.

## Run

```bash
bash run_example.sh
```

Creates `work/` next to this README (deleted and recreated on every run):

```
work/
├── input/           paper.pdf, case.json (case_id synthetic-demo-004), task.md
├── work/            paper.txt, tables/table-1.csv, tables.json,
│                    figures/fig-1.png, figures.json,
│                    charts/chart-1.png + chart-1.provenance.json,
│                    replot_spec.json, plan.json, plan_bad.json,
│                    number_audit_bad.json
└── app-output/      presentation.pptx, number_audit.json, result.json,
                     tables/, charts/   (+ presentation.pdf, preview/ if soffice exists)
```

## What the script demonstrates

1. `make_fixture.py` — synthetic paper with a 3-row table (each cell placed at
   an absolute x-position so `pdftotext -layout` yields clean columns) and a
   vector figure; also writes `case.json`, `task.md`, `replot_spec.json`, a
   good `plan.json` and a sabotaged `plan_bad.json`.
2. Early partial `result.json` secured **before** the pipeline (status
   `partial`), then `table_mine` (expect `status: mined`), `figure_harvest`,
   `replot --example-mode`, `number_audit` (expect PASS), `build_deck`, and a
   final `result.json` (status `success`, `"synthetic_example": true`).
3. **Negative demo** (part of the example, not a failure): `plan_bad.json`
   contains the hallucinated claim "accuracy of 97.1%". The script runs the
   audit on it, expects exit code 1, verifies the message names `97.1`, and
   only then succeeds.
4. An artifact listing closes the run. Expected results are in
   [expected_output.md](expected_output.md).

The deck title starts with `SYNTHETIC EXAMPLE —`, the chart footnote carries
`(synthetic demo)`, and `result.json` carries `"synthetic_example": true`.
