---
name: visual-evidence-reader
description: Directly read visual evidence in PDF figures, plots, axes, captions, legends, error bars, and tables; calibrate pixel measurements and preserve uncertainty when PDF text extraction is blind to visual content.
---

# Visual Evidence Reader

Use this skill to inspect rendered visual evidence and assess the supplied claims. It is not a downstream report renderer and not a citation-substring checker. A claim is a hypothesis to verify, never an established fact. Topical relevance alone is not support, silence is not contradiction, and conflicting observations must be reported side by side.

## Runtime contract

- The skill root is `/skills/weekly-skill`; case material is under `/input` and includes `case.json`, `task.md`, `claims-to-verify.json`, and the actual PDFs/materials.
- Use `/app/work` for rendered pages, receipts, measurements, and intermediates. Write `/app/output/result.json` as early as possible, then refine it. Aim to reserve enough of the 900-second budget and 64-request budget for validation and an honest partial result.
- The result must contain the exact `case_id`, every field required by `case.json.output_contract` at the top level, and `status`, `sources`, `uncertainty`, and `change_records`. The contract may be a list or a dictionary; never hard-code a field set.
- Claim verdicts are exactly `supported`, `partially_supported`, `contradicted`, or `insufficient_evidence`. Use run-level `status: partial` whenever material work, precision, rendering, or evidence remains incomplete. Do not hide an unfinished run behind `complete`.

## Procedure

1. Read the task, case, claims, and output contract. Create an initial adaptive skeleton:

   ```bash
   python3 /skills/weekly-skill/scripts/visual_evidence.py scaffold --case /input/case.json --output /app/output/result.json
   ```

2. Inventory the material and identify which pages and claims need visual inspection. Text-layer extraction may locate pages or captions, but cannot establish pixels, line positions, axis scales, legend mappings, or visual table layout.
3. Render every page used as figure evidence with the existing `pdftoppm`; do not infer its content from the PDF filename or text layer:

   ```bash
   python3 /skills/weekly-skill/scripts/visual_evidence.py render-pdf --pdf /input/PAPER.pdf --page 3 --dpi 250 --output-dir /app/work/page-0003 --receipt /app/work/page-0003/receipt.json
   ```

   The receipt records the PDF hash, rendered PNG hash, byte count, dimensions, page, and DPI. A receipt alone is not an observation.
4. **The Agent must open and visually inspect each rendered image used for a visual assertion.** Record what was actually seen. Never claim to have seen an unrendered, unopened, unavailable, failed, blank, or tool-inaccessible image. Only after actual image opening, attest the observation on the hash-verified receipt:

   ```bash
   python3 /skills/weekly-skill/scripts/visual_evidence.py mark-opened --receipt /app/work/page-0003/receipt.json --observer 'Agent opened page 3 PNG with the image tool' --actually-opened
   ```

   The flag is a truthful attestation, not a substitute for the visual-tool operation. If visual access fails, retain useful text evidence separately and mark visual claims `insufficient_evidence` or the run `partial`.
5. Read the panel label, complete caption, axis titles/units, tick labels, linear/logarithmic scales, legend, series/group, color/marker mapping, and error bars before measuring. For numeric extraction, create a measurement JSON following `references/visual-protocol.md`. Distinguish image pixels from figure/data coordinates and record both when available.
6. Recompute every numeric readback from independently recorded calibration points:

   ```bash
   python3 /skills/weekly-skill/scripts/visual_evidence.py readback --receipt /app/work/page-0003/receipt.json --measurement /app/work/page-0003/measurement.json --output /app/work/page-0003/readback.json
   ```

   Use at least two distinct, well-separated points per one-dimensional axis. For `affine2d`, use at least three non-collinear points. Log calibration requires strictly positive data values and reports residuals in transformed and original units. Reject degenerate geometry rather than silently regularizing it. Check calibration residuals against the task precision and the image resolution.
7. Treat graph values as estimates. Record pixel uncertainty, propagated value uncertainty, quantization error, residuals, obscuration, legend/group and error-bar meaning. Low resolution, compression, overlap, clipping, or occlusion permits only a defensible interval or `insufficient_evidence`. Never relabel an image readback as an exact table value from the paper. Exact-equality claims finer than demonstrated precision are not established by a matching rounded readback.
8. For tables, record each cell with row/column indices and the complete header path, including multi-level headers. Carry repeated or continued headers across pages. Do not invent cells hidden by page breaks or assume a unit absent from the header/caption.
9. Assign verdicts per claim and per material subclaim. Cite concrete visual sources and conflicts; if sources disagree, include each conflicting observation and its provenance rather than choosing silently. `partially_supported` means only some material components are supported, not that the evidence is topically related. `contradicted` requires affirmative incompatible evidence; `not reported` alone is insufficient for contradiction.
10. Merge readbacks into the dynamic skeleton, preserve all contract fields, validate, and rewrite the final result:

   ```bash
   python3 /skills/weekly-skill/scripts/visual_evidence.py validate-result --case /input/case.json --result /app/output/result.json
   ```

Keep the final response focused on claim findings and calibrated visual evidence. Do not turn the output into a styling exercise, and do not perform substring-only citation verification.

## Synthetic example

`examples/source.csv` is wholly SYNTHETIC source data. Run:

```bash
bash /skills/weekly-skill/scripts/run_example.sh /app/work/visual-example
```

The optional single argument is the output directory. Prefer a location outside the skill bundle. The example generates a raw PNG, synthetic paper text and claims, independent approximate-pixel measurements, calibrated readback, quantitative source comparison, annotated PNG and SVG, and a final partial result. It demonstrates software and measurement flow only; it is not Agent visual observation and does not reproduce a real paper. See `examples/EXPECTED.md`.
