# Expected output — synthetic example (合成示例)

All content is invented and marked SYNTHETIC. After `bash run_example.sh`
the `output/` directory contains:

| artifact | what it proves |
|---|---|
| `presentation.pptx` | Valid zip; 4 slides (5 − 2 deletions + 1 donor clone); merged "Background & Motivation" slide keeps 88.1% and 4.2; results slide re-voiced for the advisor keeps 92.3% / 4.2 / 88.1% / 3.5 / 1,000; title slide text hash unchanged (untouched). |
| `refit_audit.json` | `verdict: PASS` — numeric conservation (new tokens: none; dropped 90.0%/12/1e-3 declared on the backup-slide deletion), terminology conserved, untouched slide byte-identical, slide count 4 == target 4. |
| `terms.json` | Non-empty locked table from `paper.txt` (SynGraph/SG, graph kernel/GK, QSAR, chirality-aware, Weisfeiler-Lehman, …). |
| `result.json` | `case_id: synthetic-demo-003`, all six `output_contract` fields present, `status: success`, `synthetic_example: true`. |
| `presentation.pdf` | Only when `soffice` is installed; otherwise the run notes the graceful degradation. |

The negative demo (under `work/negative_demo/`, not a deliverable) applies
`refit_ops_bad.json`, whose results bullet fabricates **97.1%**. The audit
must exit 1 and name the fabrication, e.g.:

```
conserve_check verdict: FAIL (1 checks failed)
  FAIL: NEW number '97.1%' (x1) not found in paper text and not declared in any op's introduced_numbers
negative-demo conserve_check exit code: 1 (expected 1)
```

`run_example.sh` asserts all of the above; any deviation fails the script.
