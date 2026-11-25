# SYNTHETIC example — not a formal case

This independently authored example demonstrates a feed/pump/reactor/detector apparatus, control relationships, activation and inhibition markers, and a two-series chart driven by actual columns and values in `input/chart.csv`. Every scientific-looking statement and number is simulated; none is evidence for an experiment.

## Input

- `input/case.json`: synthetic case ID and three required top-level output-contract keys.
- `input/source_spec.json`: deterministic apparatus topology, layout hints, CSV mapping, source disclosure.
- `input/chart.csv`: six synthetic records with `residence_time_min`, `response_pct`, and `purity_pct`.
- `input/edits.json`: exact operations used in the separate byte-preserving edit demonstration.
- `figure/figure.svg`: pre-rendered text-only example for quick inspection; regenerate it rather than treating it as a fixed answer.

## Run

```bash
python3 scripts/run_example.py \
  --example-dir examples/synthetic \
  --output-dir /tmp/vector-publication-studio-example \
  --preview-png /tmp/vector-publication-studio-example/preview.png \
  --pdf
```

`--example-dir`, `--output-dir`, and `--preview-png` are explicit and required. `--pdf` is optional. The command fails nonzero if generation, patching, export, or validation fails.

Outputs include `figure.svg`, `source_spec.json`, copied `chart.csv`, `layout_manifest.json`, `preview.png`, optional `figure.pdf`, `export_qc.json`, `result.json`, plus a separate `figure-edited.svg` and `edit_report.json`. The edit report demonstrates a byte-span text/attribute patch, not an SVG rebuild. Fonts are live and **not embedded**.
