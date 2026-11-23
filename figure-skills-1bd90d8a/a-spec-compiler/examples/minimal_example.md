# Minimal worked example (示例 / EXAMPLE — synthetic data, not a real case)

> 本示例全部使用合成数据，仅用于说明接口与流程；所有数值均为虚构示例值。
> All data below are synthetic and illustrative; nothing here is an official
> test case or a prepared answer.

Layout: put these files in one working directory, e.g. `/app/work`.
`$SKILL_DIR` = the skill directory.

## 1. Chart mode (grouped bar, file-bound)

`data.csv` (synthetic; note the deliberately empty cell at row 1 → gap demo):

```csv
group,control,treated,control_sd,treated_sd
WT,1.00,1.42,0.08,0.11
KO,0.62,,0.07,
Rescue,0.91,1.20,0.05,0.09
```

`figure.spec.json`:

```json
{
  "version": "1.0",
  "case_id": "demo-case-001",
  "title": "示例 Demo grouped bar",
  "canvas": {"width_mm": 90, "height_mm": 70, "background": "#ffffff"},
  "mode": "chart",
  "chart": {
    "type": "grouped_bar",
    "axes": {
      "x": {"label": "Genotype", "scale": "categorical"},
      "y": {"label": "Expression", "unit": "fold change", "scale": "linear"}
    },
    "series": [
      {"name": "control", "glyph": "bar", "error_meaning": "SD",
       "data": {"source": {"path": "data.csv", "format": "csv",
                           "column_x": "group", "column_y": "control",
                           "column_yerr": "control_sd"}}},
      {"name": "treated", "glyph": "bar", "error_meaning": "SD",
       "data": {"source": {"path": "data.csv", "format": "csv",
                           "column_x": "group", "column_y": "treated",
                           "column_yerr": "treated_sd"}}}
    ],
    "annotations": [{"text": "n=3", "x": "WT", "y": 1.6,
                     "anchor": "middle", "source_locator": "data.csv#note"}],
    "legend": {"position": "top-right"}
  }
}
```

Commands:

```bash
python3 $SKILL_DIR/scripts/validate_spec.py figure.spec.json --report validate_report.json
python3 $SKILL_DIR/scripts/compile_figure.py figure.spec.json \
  --out-svg figure.svg --ledger mapping_ledger.json
python3 $SKILL_DIR/scripts/export_preview.py figure.svg \
  --out-dir . --manifest export_manifest.json
```

### What gets produced (verified on python3.12 + LibreOffice + poppler)

`figure.svg` — 90mm × 70mm, `viewBox="0 0 90 70"`, layers:

```
layer-background · layer-panel0-grid · layer-panel0-axes ·
layer-panel0-series-control · layer-panel0-series-treated ·
layer-panel0-annotations · layer-panel0-legend · layer-title
```

Every bar is `<rect class="glyph" data-src="…/data.csv#column=control,row=0"
data-value="1">` — text stays `<text>`, nothing is outlined. The empty
`treated` cell at row 1 becomes a ledger `bar-gap` entry (`missing_value`);
no bar is drawn and nothing is averaged or invented. Y axis: nice ticks
0 / 0.5 / 1 / 1.5 / 2. Legend entries read `control (error: SD)` /
`treated (error: SD)` because `error_meaning` was declared.

`mapping_ledger.json` — excerpt (one of 7 glyphs):

```json
{
 "glyph_id": "g001",
 "layer": "layer-panel0-series-control",
 "kind": "bar",
 "values": {"x": "WT", "y": 1.0, "yerr": 0.08},
 "source": {"path": "…/data.csv", "column": "control",
            "column_x": "group", "row": 0,
            "key": "…/data.csv#column=control,row=0"},
 "transform": "y_mm = 60.5 + (v-(0))/((2)-(0))*-49.5",
 "uncertain": false, "notes": []
}
```

plus `source_index` (reverse map: source cell → glyph ids, e.g.
`"…/data.csv#column=control,row=0": ["g001"]`) and a `warnings` array.
Recompiling the same spec yields a **byte-identical** SVG.

`export_manifest.json` — excerpt:

```json
{"status": "ok",
 "tool_versions": {"soffice": "LibreOffice 26.2.x", "pdftoppm": "25.01.0",
                   "fc-list": "NOT FOUND"},
 "font_summary": {"available": false,
                  "note": "fc-list not found; font check skipped…"},
 "outputs": [{"path": "…/figure.pdf", "format": "pdf", "via": "soffice"},
             {"path": "…/figure.png", "format": "png", "dpi": 300,
              "via": "pdf->pdftoppm"}],
 "deviations": []}
```

On a machine without soffice the same command exits 0 with
`"status": "renderer_unavailable"` and a deviation explaining that PDF/PNG
were not produced — disclose that in result.json.

## 2. Diagram mode (3-node pathway A→B, C⊣B)

`diagram.spec.json` (locators point at a pretend paper — illustrative):

```json
{
  "version": "1.0", "case_id": "demo-case-001", "mode": "diagram",
  "canvas": {"width_mm": 100, "height_mm": 70, "background": "#ffffff"},
  "diagram": {
    "title": "示例 pathway A→B⊣C",
    "compartments": [{"id": "cyto", "x": 5, "y": 5, "w": 90, "h": 90,
                      "label": "cytoplasm", "manual": true}],
    "nodes": [
      {"id": "A", "shape": "rounded_rect", "x": 20, "y": 30, "w": 22, "h": 12,
       "label": "KinaseA", "source_locator": "paper.pdf#page=2,para=1"},
      {"id": "B", "shape": "ellipse", "x": 60, "y": 30, "w": 24, "h": 14,
       "label": "FactorB", "source_locator": "paper.pdf#page=2,para=1"},
      {"id": "C", "shape": "rounded_rect", "x": 60, "y": 70, "w": 24, "h": 12,
       "label": "InhibitorC", "source_locator": "paper.pdf#page=3,fig1",
       "uncertain": true}
    ],
    "edges": [
      {"from": "A", "to": "B", "style": "arrow", "label": "phosphorylates",
       "source_locator": "paper.pdf#page=2,para=2"},
      {"from": "C", "to": "B", "style": "tbar",
       "source_locator": "paper.pdf#page=3,fig1"}
    ],
    "legend": {"position": "bottom-left", "items": [
      {"label": "activates", "style": "arrow", "manual": true},
      {"label": "inhibits", "style": "tbar", "manual": true}]}
  }
}
```

Same three commands. Result: compartment rect painted behind nodes; A→B arrow
with label; C⊣B T-bar (inhibition) ending on B; InhibitorC drawn with a
dashed outline because `uncertain: true` (and flagged in the ledger); legend
with edge-style swatches. Layers: `layer-background, layer-compartments,
layer-edges, layer-nodes, layer-legend, layer-title`.

## 3. result.json round-trip

```bash
python3 $SKILL_DIR/scripts/make_result.py --case case.json \
  --out result.json --status partial --note "intake"
# … work …
python3 $SKILL_DIR/scripts/make_result.py --case case.json \
  --out result.json --status complete \
  --source "data.csv#columns=group,control,treated (synthetic demo)" \
  --note "final: grouped bar + pathway diagram compiled and exported"
```

`case.json` here was `{"case_id": "demo-case-001", "output_contract":
{"editable_source": "…", "exports": "…", "figure_summary": "…"}}`; the script
guarantees those three keys exist, keeps real content across runs, and appends
timestamped `change_record` entries. Dict / list-of-strings / list-of-dicts
contract shapes are all accepted.
