# SYNTHETIC enzymatic assay example

**SYNTHETIC SOFTWARE FIXTURE ONLY — not experimental evidence, not a real primary biological source, not an official case, and not a prepared answer.** Every compound, observation, and numeric value is invented for testing. The CSV is real UTF-8 tabular input parsed by code; its values remain synthetic.

## Input inventory

- `input/case.json`: example identity and output contract.
- `input/task.md`: synthetic drawing workorder.
- `input/semantic_graph.json`: primary typed semantic artifact, compartments/ports/interactions/phases/source transcription.
- `input/source/figure03.svg`: synthetic source-like original used to test semantic rather than pixel comparison.
- `input/source/caption.md` and `methods.md`: supporting synthetic text.
- `input/data/assay.csv`: four headers and ten data rows.

## Supported relationships only

1. Synthetic substrate S has material flow into E-catalysed conversion.
2. Conversion has material flow to synthetic product P.
3. Synthetic enzyme E catalyses the process (not substrate flow).
4. Synthetic inhibitor I inhibits the process with a blunt bar. No competitive/noncompetitive/irreversible or feedback mechanism is supported.
5. Reaction precedes synthetic absorbance measurement of product formation.
6. Measurement supplies the actual CSV records to a two-series chart.

The source figure and final generated figure differ in layout but share these relationships. No biological knowledge should be added.

## Actual CSV mapping

Headers are `condition,time_min,product_uM,replicate_label`.

- x: `time_min`;
- y: `product_uM`;
- series: `condition` = `control` and `with_inhibitor` (five rows each);
- `replicate_label` is intentionally unplotted.

The renderer performs no fitting, smoothing, aggregation, interpolation, or invented points. Output points carry original CSV line and x/y values.

## Run and expected checks

From the bundle root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_example.py \
  --example-dir examples/synthetic \
  --output-dir /app/output/synthetic \
  --preview-png /app/output/synthetic/synthetic-preview.png \
  --preview-pdf /app/output/synthetic/synthetic-preview.pdf
```

Expected: exit 0, zero semantic errors, seven required nodes, six interactions, ten CSV records, source semantic status `match`, layered editable SVG, and result contract keys at top level. PNG/PDF production depends on an available optional exporter. The retained verified run used installed Google Chrome for both formats; `export_report.json` records one real PDF page with valid signature/EOF plus valid PNG signature/IEND.
