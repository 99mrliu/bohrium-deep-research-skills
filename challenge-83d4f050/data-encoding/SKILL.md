---
name: data-encoding
description: Derive statistically traceable data charts from raw CSV/TSV/JSON with replicate-aware mean/SD/SEM, configured log2FC/-log10p, explicit visual scales, row provenance, stable SVG marks, and source-preserving ID edits.
---

# Data encoding

Use this skill when the chart must be derived from **actual upstream data**, not from hand-transcribed statistics or decorative evidence claims. It connects raw observations → independent-sample statistics → derived tidy tables → scales/marks, and audits that chain. It supports bar and scatter charts plus fill, size, and edge-width channels.

## Formal run contract

Never substitute the synthetic example for missing formal input.

```bash
python3 /skills/weekly-skill/scripts/run.py \
  --input /input --work /app/work --output /app/output
```

Required files are `/input/case.json`, non-empty `/input/task.md`, a workorder (default `/input/workorder.json`), a data spec (default `/input/spec.json`), and the raw CSV/TSV/JSON named by that spec. Do not alter authoritative input: stage copies under `/app/work/staged`, add only source-derived spec/workorder there, preserve original `case_id` and `output_contract`, then use `--input /app/work/staged`. Relative spec/raw paths resolve against `/input`; a relative raw `path` resolves against the spec file. Optional `source_svg`/`figure03` or `source_pdf`/`original_pdf` and zero-based `source_page` enable source edits; PDF-to-SVG extraction uses PyMuPDF in `/app/work`.

The **data spec is restricted to paths, column names, filters, and transforms**. It has no keys for means, SD, SEM, p summaries, chart aesthetics, or hand-copied result values. The separate workorder controls chart type and encoding. See [references/data_spec.md](references/data_spec.md) and [references/visual_channels.md](references/visual_channels.md).

Every output_contract field is retained at result top level and under `output_contract`; `case_id`, dynamic `status`/`partial`, `editable_source`, `export_artifact`, `content_map`, `compliance_checks`, `exceptions`, generated files, per-file hashes/format checks, actual sources, uncertainties, changes, and errors are added. Standard outputs are `derived.csv`, `group_summary.csv`, `data_audit.json`, `chart.svg`, `chart.png`, `chart.pdf`, `sources.json`, `uncertainty.json`, `change_records.json`, and `result.json`; safe relative filenames can be remapped with `output_contract.artifacts`.

Exit 0 means all required artifacts passed checks. Missing columns, illegal/non-finite numbers, invalid transforms/scales, unknown IDs, and rendering failures return non-zero (normally 2) with an honest `status: "partial"` result and only actual artifacts. There is no silent imputation or success-by-placeholder.

## Statistics and provenance

1. Apply configured filters, then validate required numeric fields as finite. Raw JSON NaN/Infinity is rejected. A deliberately excluded row does not contribute values.
2. A sample is a unique configured sample ID within `(feature, group)`. Average repeated rows **within each sample first**.
3. Group mean is the mean of those sample means. `n_samples` counts independent samples, not raw rows. SD is sample SD (`ddof=1`) of sample means; SEM is `SD / sqrt(n_samples)`. SD/SEM are null for `n<2`.
4. `log2FC` is either read from an unambiguous configured raw feature column or computed as `log2((numerator_group_mean + pseudocount)/(denominator_group_mean + pseudocount))` from the derived group means. `-log10p` comes only from the configured raw p column; p=0 uses the declared positive floor and is flagged. The runner does **not** invent a statistical test or fabricate p-values.
5. Every derived observation retains source file SHA-256, raw source row number, and a SHA-256 checksum of the canonical raw row object. Filtered rows and reasons remain in `data_audit.json`. CSV/TSV row numbers count the header as line 1; JSON rows use 1-based array order.

`derived.csv` is observation-level tidy output with sample/group statistics and realized fill/size. `group_summary.csv` contains independent-sample summaries. The audit includes group/feature values, transform/filter configuration, all row provenance, every scale domain/range/policy, and every stable mark's realized encoding.

## Visual channels

Every SVG bar, sample circle, and edge has a stable ID (`bar-*`, `sample-*`/`point-*`, `edge-*`). Labels, ticks, and legends are real SVG `<text>`. PNG/PDF are genuinely rendered from the SVG via PyMuPDF.

Legends are generated from actual category/color mappings. Continuous domain defaults to observed data min/max and is labeled `observed data`; an explicit workorder domain is labeled `configured`, with observed domain still audited. Fill can be categorical or continuous color interpolation. Size and edge-width are linear numeric mappings with declared ranges. Missing values use an explicit fallback or are skipped; out-of-range values are clamped, skipped, or (categorical fill) given a declared fallback. Counts of missing/out-of-range/skipped marks are audited. No invisible default imputation is allowed. Any chart with edges must explicitly define `channels.edge_width`.

Inspect the PNG for readable labels, appropriate error bars, accurate legend values, clipping, and whether the selected channels answer the scientific question. See [references/visual_channels.md](references/visual_channels.md) for chart fields and limitations.

## Source-preserving SVG edits

Set `case.mode: "edit"` and provide a source SVG/PDF. Workorder must explicitly describe `changed` and `unchanged`, then use exact IDs:

```json
{
  "changed": ["chart-title text", "bar-FEATURE-Control fill"],
  "unchanged": ["All other source SVG subtrees", "Raw data and spec"],
  "operations": [
    {"op": "update_svg_text", "id": "chart-title", "text": "Edited title"},
    {"op": "update_svg_attr", "id": "bar-FEATURE-Control", "name": "fill", "value": "#3b78a8"}
  ]
}
```

Text targets must be text/tspan/title/desc. Event handlers and external attributes are rejected. Non-target subtrees are compared before/after; with no SVG operation the source bytes are preserved exactly. `change_records.json` logs before/after values and changed/unchanged scope.

A preserved source chart is **not silently regenerated to match new data**. Derived tables and the candidate scale registry still reflect the raw data, and an uncertainty warning states that the source visual may differ. Use create mode without `source_svg` for synchronized data-driven marks.

## Synthetic test and references

All data and labels in `examples/SYNTHETIC/` are fabricated for testing only. The example has two biological-sample groups, four independent samples per group, two repeated measurements per sample, raw p/log2FC columns, SEM bars, categorical fill, numeric size and edge width.

Read [references/data_spec.md](references/data_spec.md), [references/visual_channels.md](references/visual_channels.md), and [references/contracts.md](references/contracts.md). Dependencies: Python 3.10+ and PyMuPDF (`import pymupdf`); ingestion and statistics otherwise use the standard library. Matplotlib is not required.
