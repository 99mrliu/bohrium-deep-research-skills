# Source Span Atlas

An upstream-source-authenticity Skill for scientific apparatus, technical-route, mechanism/flow, simple CSV chart, and source-preserving SVG editing tasks. **Exact span matching is deliberately separate from scientific semantic comparison.** The bundle has no prepared official case answers.

## What it does

- Resolves unique exact quotes after NFKC, canonical quote/dash, and whitespace normalization, with original/normalized offsets plus page/line/section/figure locators and source hashes.
- Requires explicit/inferred/unsupported status, a separate semantic review, direct original-figure inspection records, and conflict treatment. Unsupported assertions, inferred connections, and unresolved conflicts block.
- Supports real text-layer PDF methods using available `pdftotext`, actual original Figure 03/PDF/PNG review hashes, and actual case-sensitive CSV header/value/row mappings.
- Generates simple editable layered SVG only after a pass, or audits an existing SVG without rebuilding it. Targeted XML patch helper preserves all original bytes outside edit ranges and reports before/after changes.
- Emits `atlas.json`, `report.md`, `result.json`, editable SVG, and optional honestly detected PNG and/or PDF exports. `result.json` copies every `output_contract` key to top level and records status/sources/uncertainties/change_records.

## Dependencies and limits

Core: **Python 3 standard library only**. No installation, service, model API, or network access is needed by the scripts. PDF text extraction requires preinstalled `pdftotext` or a native environment alternative. Optional PNG/PDF export detects CairoSVG + native Cairo, `rsvg-convert`, Inkscape, then headless Chrome/Chromium; PDF browser detection accepts an executable in `SOURCE_SPAN_ATLAS_BROWSER` or autodetects Chrome/Chromium on PATH and in standard application locations. No installs are attempted. PDF export checks header, EOF, page/tree objects and counts, MediaBox dimensions, and `startxref`; these structural checks are not visual inspection. OCR is not implemented by the core.

The simple renderer is not a dense autorouter, scientific inference engine, fitting tool, publication preflight suite, or font embedder. It handles straightforward rows/edges, notes, and two-numeric-column line/scatter charts in CSV order. No imputation/fitting, missing-flow completion, arbitrary scientific judgement, CMYK conversion, or guaranteed font availability. SVG text uses `Arial, Helvetica, Noto Sans CJK SC, Microsoft YaHei, sans-serif`; inspect actual exports for substitution/tofu/clipping. Missing exports produce honest `partial`, not fake success.

All bundled files are UTF-8 text. Original binary PDFs/PNGs appear only in the caller's runtime inputs/outputs, not in this bundle.

## Run the SYNTHETIC minimal example

**All bundled example materials and values are SYNTHETIC, not an experiment and not an official result.**

```bash
SKILL_DIR=/path/to/source-span-atlas
python3 "$SKILL_DIR/scripts/run_example.py" \
  --example-dir "$SKILL_DIR/examples/minimal" \
  --output-dir /app/work/source-span-example
```

Optional installed-export previews (paths chosen by caller; flags are independent):

```bash
python3 "$SKILL_DIR/scripts/run_example.py" \
  --example-dir "$SKILL_DIR/examples/minimal" \
  --output-dir /app/work/source-span-example \
  --preview-png /app/work/source-span-example/figure.png \
  --preview-pdf /app/work/source-span-example/figure.pdf
```

For PDF export, set `SOURCE_SPAN_ATLAS_BROWSER=/absolute/path/to/installed/browser` only when autodetection does not find an installed Chrome/Chromium. The same variable can supply a browser for PNG export.

Both path flags are explicit and required. Absolute paths are recommended. For portability and cwd independence, relative CLI paths are resolved beside each script; atlas source paths resolve beside `input/atlas.json`. The runner refuses to put generated files inside the fixture.

Outputs:

- `figure.svg`: real editable SVG with named layers, stable scientific group IDs, source IDs, assertion IDs, evidence statuses, and text labels.
- `atlas.json`: primary artifact containing source hashes/spans/locators, separate semantics, Figure 03 direct review, CSV rows, conflicts, errors, and source-to-visual coverage.
- `report.md`: readable evidence/coverage/gate atlas report.
- `result.json`: `case_id`, top-level contract keys, status, sources, uncertainties, change_records, artifacts, and optional exports.
- `export_report.json`, optional `figure.png`: actual PNG attempts/results, output dimensions, font/color notes.
- `pdf_export_report.json`, optional `figure.pdf`: actual PDF attempts/results, structural checks, page dimensions/count, SHA-256, and inspection/font/color notes.
- `example_run_report.json`: expected core-output comparisons, separate requested-export checks, and top-level contract check.

`examples/minimal/expected/` contains expected SVG/JSON/Markdown. `<OUTPUT_DIR>` replaces the run directory to avoid embedding author-machine paths. CairoSVG and headless-browser rendering may differ visually across hosts; deterministic comparisons are for core SVG/JSON/Markdown, not PNG/PDF bytes. Export-only result additions are compared separately so supplied exports do not break the core fixture comparison; a failed requested export still fails the example wrapper.

The synthetic original `input/sources/original_figure03.svg` is itself text/editable and has no binary fixture. Its original and output previews can be generated with the optional exporter and visually inspected. No pump, waste, bypass, or recycle connection is drawn because the synthetic methods explicitly exclude them.

## Run a real atlas

```bash
python3 /skills/weekly-skill/scripts/source_span_atlas.py \
  --atlas /app/work/source_atlas_input.json \
  --output-dir /app/output
```

Use `--audit-svg /app/output/edited.svg` to check source/visual coverage for a targeted edit instead of rebuilding. Independently add `--preview-png /app/output/figure.png` and/or `--preview-pdf /app/output/figure.pdf` when exporters are available. Invalid input and failed scientific gates return nonzero and still leave failed reports where possible. Valid core output with optional export failure returns the core output, preserves SVG, marks `result.json` partial, and omits the failed preview artifact. The PDF report never sets a `pdf` path after failure.

Use `references/atlas-schema.md` for complete field rules, `references/semantic-and-figure-review.md` for actual PDF/Figure 03 comparison, and `references/svg-editing-and-exports.md` for patch invocation/records. `SKILL.md` defines the full official runtime contract, `/app/work` vs `/app/output`, early checkpoint, 64-request/900-second budget, two review rounds, fonts, limits, and failure policy.

## Meaningful negative test

```bash
python3 "$SKILL_DIR/tests/run_negative.py" \
  --output-dir /app/work/source-span-negative
```

The source explicitly says no motor connection is described; the atlas deliberately invents one. The wrapper passes only if the validator itself returns nonzero, emits `UNSUPPORTED_ASSERTION`, records `verdict:"failed"`, and writes no `figure.svg`. The inner validator failure is expected and is the subject of the test.

## Resource reuse and maintenance

- Change normalization only with a schema/version update and updated expected spans. Never add approximate matching to make a case pass.
- Extend chart types only with exact source mappings and meaning/unit review; retain CSV raw values/rows.
- Extend SVG editing only with targeted XML provenance and unchanged-byte verification. Do not substitute tree-wide reserialization.
- Run the positive synthetic example after template/validator changes and regenerate expected text artifacts intentionally. Run the negative gate test after matcher changes.
- Keep every example synthetic and visibly labelled; official case material belongs only in runtime `/input`/`/app` paths.
