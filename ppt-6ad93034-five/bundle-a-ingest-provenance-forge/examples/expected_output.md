# Expected output — 合成示例 (synthetic example), not an official case result

After `cd examples && bash run_example.sh` (exit 0), the following artifacts
exist under `examples/work/`. Sizes below are from the reference run; small
variation is normal.

## work/input/ (fixture)

| File | Proves |
|---|---|
| `paper.pdf` (~4 KB) | synthetic 3-page paper exists; title text marks it synthetic |
| `case.json` | `case_id: synthetic-demo-001` + six-field `output_contract` |
| `task.md` | slide work order, labeled synthetic |

## work/work/ (intermediates)

| File | Proves |
|---|---|
| `pages/page-001.png` … `page-003.png` (each > 40 KB) | every page rendered at 150 dpi — the cross-validation substrate |
| `spans.jsonl` (~29 lines) | line-level spans with `page`, `x0..y1`, `method: pdftotext-bbox`, `reading_order` |
| `paper.txt` | spans in reading order with `[[page N]]` markers |
| `ingest_report.json` | forensics ran: 3 pages, span/char counts per page, `issues: []` on this clean fixture |
| `figures.json` | `fig-1` found via caption regex; zone bbox + `crop_path`; no tables |
| `figures/fig-1.png` (~11 KB, 1500×768) | the caption-above zone re-rendered at 200 dpi — shows the axes + descending polyline, NOT the caption or limitations text |
| `plan.json` | 4 slides, 5 bullets, each citing real span ids with verbatim quotes |
| `bindings.json` | `"ok": true`; 5 verdicts; `evidence_map` with per-bullet pages/span ids/footer |
| `build_manifest.json` | slide list, `synthetic_example: true`, `export.skipped` (no soffice on the reference machine), template note |

## work/app-output/ (deliverables)

| File | Proves |
|---|---|
| `presentation.pptx` (~20 KB, 28 zip entries) | editable 4-slide deck; valid zip (`zipfile.testzip()` → None); opens in python-pptx; slide 1 title prefixed `SYNTHETIC EXAMPLE — `; footers `p.2 · spans p2-s0008` etc.; fig-1.png embedded on slide 3; notes present |
| `result.json` | `case_id` + ALL six contract fields (`status`, `editable_source`, `export_artifact`, `content_map`, `compliance_checks`, `exceptions`), `"synthetic_example": true`, status `success`, soffice exception recorded |

If `soffice` IS available, additionally: `presentation.pdf` and
`preview/slide-*.png`, and `result.json.export_artifact` points at the PDF.

## Deliberately failing variant (fail-closed proof)

Edit `work/work/plan.json` and change one bullet's `quote` to a non-verbatim
sentence, e.g. `"accuracy of 99.9% on the SynBench test set"`, then:

```bash
python3 ../scripts/span_bind.py --plan work/work/plan.json
```

Observed (exit code 1):

```
[span_bind] FAIL: 1 problem(s); fix the plan, not the checker
[span_bind]   - s2/b1: quote is not a verbatim substring of its spans: 'accuracy of 99.9% on the SynBench test set'
```

`bindings.json` is rewritten with `"ok": false`, and a subsequent
`build_deck.py` run refuses:

```
[build_deck] REFUSING to build: bindings.json shows failures; fix the plan, not the checker
```

(exit code 1). A hallucinated-number variant (bullet text `95.1%` while the
cited span says `92.3%`) fails likewise with
`numeric token(s) ['95.1%'] absent from cited spans; refusing unverifiable numbers`.
Restore the plan (or re-run `make_fixture.py --emit-plan`) and `span_bind`
returns to `OK: 5 bullet(s) verified fail-closed` (exit 0).
