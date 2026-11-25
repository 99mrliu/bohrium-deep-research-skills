# Expected output (合成示例 / synthetic demo)

All artifacts below are produced by `bash run_example.sh` from a **fabricated**
paper; every number is invented. `run_example.sh` exits 0 only when every
positive step succeeds AND the negative demo fails the audit as designed.

## Artifacts

| Artifact | Proof |
|---|---|
| `work/tables/table-1.csv` | status `mined` in `tables.json`; 3 data rows; contains `92.3` verbatim (`SynNet (ours),92.3,0.91`); cells keep the printed header `Accuracy (%)` |
| `work/tables.json` | `[{table_id: table-1, caption: "Table 1: Test accuracy (%) on SynBench (synthetic).", page: 1, rows: 3, cols: 3, status: mined}]` |
| `work/figures/fig-1.png` | > 5 KB (≈15 KB, 1169x933 px @200 dpi); visually verified: axes + polyline + tick labels, no caption/body text |
| `work/figures.json` | `classification: "bitmap-embed"` (figure caption shares no quantity word with the mined table) |
| `work/charts/chart-1.png` | > 10 KB (≈29 KB, 150 dpi); grouped bars in palette `#1F4E79/#C0504D`; in-chart footnote `Data: Table 1 (p.1) - replotted verbatim . SYNTHETIC EXAMPLE (synthetic demo)` |
| `work/charts/chart-1.provenance.json` | `rows_used` keeps the raw printed strings (`"92.3"`, `"0.91"`); `figure_ref: "Figure 1"`, `page: 1` |
| `app-output/number_audit.json` | `overall: PASS`, `numbers_checked: 4`, per-slide PASS verdicts |
| `app-output/presentation.pptx` | valid zip; `ppt/slides/slide2.xml` contains a real `<a:tbl>` (native editable table) with bold theme-filled header and the verbatim cells; 4 slides, 4 notes parts, 2 media PNGs; title slide starts `SYNTHETIC EXAMPLE —` |
| `app-output/result.json` | `case_id: "synthetic-demo-004"` plus all six contract fields (`status: success`, `editable_source`, `export_artifact`, `content_map`, `compliance_checks`, `exceptions`) and `"synthetic_example": true` |
| `app-output/tables/`, `app-output/charts/` | copies of the CSVs / chart PNGs + provenance for delivery |
| `app-output/presentation.pdf`, `app-output/preview/` | only when `soffice` is on PATH; otherwise the skip is recorded in `result.json` exceptions |

## Negative demo (designed failure, part of the example)

`plan_bad.json` changes one bullet to the hallucinated claim
"SynNet reaches an accuracy of 97.1% on SynBench." The audit exits 1 and
prints:

```
[number_audit] FAIL s2 (table): number '97.1%' not found verbatim in paper text or mined CSVs - remove it or bind it to a source
[number_audit] overall FAIL; 4 numeric token(s) checked; report -> .../work/number_audit_bad.json
```

`run_example.sh` asserts the exit code is exactly 1 and that the message
names `97.1`; `build_deck.py` would refuse to build on this audit
(`number audit is 'FAIL', not PASS; refusing to build - fix the plan, not
the checker`).
