# Authoring figure.spec.json — practical guide

The spec is the ONLY hand-written artifact. Everything else (SVG, ledger,
previews) is generated. Schema: `spec_schema.json` (same directory as this
guide, one level up).

## 1. Choosing mode and chart type

| Case pattern | mode | chart.type / shapes |
|---|---|---|
| numeric table → bars per condition, ≥1 grouping variable | chart | `grouped_bar` |
| measurement vs. dose/time/concentration | chart | `line` (trend) or `scatter` (raw points) |
| mechanism / pathway / flow / schematic (figure03) | diagram | nodes + edges + compartments |
| edit of an existing figure | same mode as original | reproduce original encodings, then apply the requested change in the spec |

Rules of thumb:
- Use `grouped_bar` when x is categorical; use `line`/`scatter` when x is
  numeric and ordered. A `line` chart also accepts `"scale": "categorical"` x.
- One y unit per axis. If series disagree in units, convert in the DATA (and
  say so via `derived`), or split into panels (`panels: [...]`, each panel its
  own axes). The validator warns on unit mismatches.
- Magnitude span > ~1e6 on one axis → `"scale": "log"` (y only). Non-positive
  values on a log axis are skipped with a ledger note — that is a red flag to
  reconsider, not to ignore.
- Bar charts always include a zero baseline automatically (unless log); do not
  truncate bar axes with `min` — it visually lies about ratios.

## 2. Binding data

Two forms; prefer `source` whenever a data file exists.

File-bound (row indices are 0-based AFTER the header):

```json
"data": {"source": {"path": "measurements.csv", "format": "csv",
                    "column_x": "genotype", "column_y": "fold_change",
                    "column_yerr": "sd", "rows": [0, 1, 2, 3]}}
```

Paths are resolved relative to the spec file directory (keep data next to the
spec in /app/work, or copy it there). `format` may be csv/tsv/json
(json = list of records or dict of columns).

Inline transcription (only when numbers come from a paper table/figure and no
machine-readable file exists — the locator is then MANDATORY):

```json
"data": {"values": [{"x": "WT", "y": 1.00, "yerr": 0.08},
                    {"x": "KO", "y": 0.62, "yerr": 0.07}],
         "source_locator": "paper.pdf#page=4,table=2"}
```

`"y": null` = missing value → the compiler draws a gap and logs
`missing_value`. Error bars REQUIRE `"error_meaning": "SD" | "SEM" | "95% CI"`
so the legend can state it honestly (validator warns otherwise).

## 3. Source locators

Format: `<file>#<where>` — free text after `#`, but be precise and consistent:

- data files: `data.csv#column=fold_change,row=3` (this is exactly what the
  compiler stamps into `data-src`; write the same style in your notes)
- PDFs: `paper.pdf#page=4,table=2,row=3` or `paper.pdf#page=6,fig3,panel=B`
  or `paper.pdf#page=2,paragraph=3`
- Use the `pdftotext -layout` output to count pages (`\f` page breaks) and to
  identify tables; when the text layer garbles a table, render that page with
  `pdftoppm -png -r 100` and read the number off the image — the locator still
  points at the PDF page.

**Every number needs a locator.** If you cannot find one, the number does not
go on the figure. Derived quantities carry `"derived": "ratio col B / col A"`.
Pure layout/styling decisions carry `"manual": true` — never use `manual` to
excuse a missing data source.

## 4. Entities and labels

- Copy entity names **verbatim** from the source (gene/protein/species/compound
  spelling, capitalization, hyphens, Greek letters). Gene italics cannot be
  reliably mixed inside SVG text runs — keep roman text and record
  `"comment": "gene name italicized in source"` on the node if it matters.
- Labels > 60 chars trigger warnings; node labels are auto-wrapped, long
  category tick labels are rotated −40° then truncated with "…" (ledger
  warning). Shorten where the science allows.
- Non-ASCII (CJK) labels work via the font fallback stack; always confirm in
  the PNG that nothing renders as tofu, and record the risk if no CJK font was
  found (`export_manifest.json → font_summary`).
- `"uncertain": true` on any series/node/edge/annotation renders it dashed and
  records it in the ledger. Use it for values read from low-quality scans,
  relations you infer but the paper only implies, etc.

## 5. Diagram-mode layout advice (figure03-style)

- Coordinates are 0–100 relative units, y DOWN from the top. Think in a
  top-down or left-right flow: inputs/stimuli at top-left, outcomes at
  bottom/right.
- Keep node centers ≥ 12 units apart; typical node w=18–26, h=10–14.
- Draw `compartments` (nucleus, cytoplasm, membrane region…) first — the
  compiler paints them behind nodes automatically.
- Edge semantics (state them in the diagram legend):
  `arrow` = activates/promotes/leads-to; `tbar` = inhibits/blocks;
  `blunt` = plain connection/binding; `dashed` = indirect/putative.
  Use `route: "elbow"` for orthogonal pathway look, `"straight"` otherwise.
- Put a small legend explaining arrow semantics and any color coding; legend
  items are styling (`manual: true`) but the semantics must match the paper.
- Every node = an entity from the paper with `source_locator`; every edge = a
  relation stated in the paper with `source_locator`. Inferred relations:
  `dashed` + `uncertain: true`.

## 6. Worked mini-specs

Chart (grouped bar, file-bound) — see `examples/minimal_example.md` for the
complete runnable version:

```json
{"version": "1.0", "case_id": "demo", "mode": "chart",
 "canvas": {"width_mm": 90, "height_mm": 70},
 "chart": {"type": "grouped_bar",
   "axes": {"x": {"label": "Genotype"},
            "y": {"label": "Expression", "unit": "fold change"}},
   "series": [{"name": "control", "glyph": "bar", "error_meaning": "SD",
     "data": {"source": {"path": "data.csv", "column_x": "group",
                         "column_y": "control", "column_yerr": "control_sd"}}}],
   "legend": {"position": "top-right"}}}
```

Diagram (3-node pathway A→B, C⊣B):

```json
{"version": "1.0", "case_id": "demo", "mode": "diagram",
 "canvas": {"width_mm": 100, "height_mm": 70},
 "diagram": {"title": "示例 pathway (illustrative)",
   "nodes": [
     {"id": "A", "shape": "rounded_rect", "x": 20, "y": 30, "w": 22, "h": 12,
      "label": "KinaseA", "source_locator": "paper.pdf#page=2,para=1"},
     {"id": "B", "shape": "ellipse", "x": 60, "y": 30, "w": 24, "h": 14,
      "label": "FactorB", "source_locator": "paper.pdf#page=2,para=1"},
     {"id": "C", "shape": "rounded_rect", "x": 60, "y": 70, "w": 24, "h": 12,
      "label": "InhibitorC", "source_locator": "paper.pdf#page=3,fig1",
      "uncertain": true}],
   "edges": [
     {"from": "A", "to": "B", "style": "arrow", "label": "phosphorylates",
      "source_locator": "paper.pdf#page=2,para=2"},
     {"from": "C", "to": "B", "style": "tbar",
      "source_locator": "paper.pdf#page=3,fig1"}],
   "legend": {"position": "bottom-left", "items": [
     {"label": "activates", "style": "arrow", "manual": true},
     {"label": "inhibits", "style": "tbar", "manual": true}]}}}
```

Multi-panel: replace `chart` with `"panels": [ {…panel…}, {…panel…} ]` and
optional `"layout": {"cols": 2}`. Give each panel a short `title` ("A", "B"…).
