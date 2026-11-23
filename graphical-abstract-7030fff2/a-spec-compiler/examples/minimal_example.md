# Minimal example (EXAMPLE — not a formal case result)

Demonstrates the full Bundle A loop on a synthetic 3-line material file.
All commands assume the skill is at `/skills/weekly-skill` and inputs at
`/input`; here they are shortened.

## Input

`/input/case.json`:

```json
{"case_id": "demo-spec-001", "task": "graphical_abstract",
 "output_contract": {"fields": ["case_id", "status", "editable_source",
  "export_artifacts", "content_map", "compliance_checks", "exceptions",
  "sources", "uncertainty", "change_record"]}}
```

`/input/material.txt`:

```
We treated HeLa cells with 5 uM staurosporine for 6 h and observed caspase-3 activation.
Cell viability decreased from 100% to 42% after treatment, measured by CCK-8 assay.
Apoptosis was confirmed by Annexin V staining.
```

`/input/viability.csv`:

```
condition,viability_pct
control,100
staurosporine_5uM,42
```

## Calls

```bash
python3 scripts/make_result.py --case /input/case.json --outdir /app/output \
    --status partial --note "run started"
python3 scripts/extract_materials.py --input /input --outdir /app/work
# -> files_seen 3, text_blocks 3, data_files 2
# author /app/work/figure_spec.json (shown condensed below)
python3 scripts/check_spec.py --spec /app/work/figure_spec.json \
    --pool /app/work/source_pool.txt --datadir /input        # -> gate PASS
python3 scripts/render_spec.py --spec /app/work/figure_spec.json \
    --outdir /app/output
python3 scripts/make_result.py --case /input/case.json --outdir /app/output \
    --status complete --gate pass --note "spec compiled"
```

## Spec sketch (condensed; full grammar in references/spec_format.md)

```json
{"case_id": "demo-spec-001",
 "title": "Staurosporine induces apoptosis in HeLa cells",
 "canvas": {"width_in": 7.2, "height_in": 3.2, "dpi": 300},
 "reading_order": ["a", "b"],
 "panels": [
  {"id": "a", "kind": "schematic", "rect_in": [0.15, 0.45, 3.9, 2.5],
   "nodes": [
    {"id": "drug", "label": "Staurosporine\n5 uM, 6 h", "role": "intervention",
     "xywh_frac": [0.02, 0.30, 0.26, 0.30], "font_pt": 8,
     "source": {"locator": "material.txt line 1",
                "quote": "We treated HeLa cells with 5 uM staurosporine for 6 h"}},
    {"id": "apop", "label": "Apoptosis\n(Annexin V+)", "role": "outcome",
     "xywh_frac": [0.70, 0.55, 0.28, 0.30], "font_pt": 8,
     "source": {"locator": "material.txt line 3",
                "quote": "Apoptosis was confirmed by Annexin V staining"}}],
   "edges": [{"from": "drug", "to": "apop", "style": "arrow",
              "source": {"locator": "material.txt line 1",
                         "quote": "observed caspase-3 activation"}}]},
  {"id": "b", "kind": "bar", "title": "Cell viability (CCK-8)",
   "rect_in": [4.35, 0.45, 2.7, 2.5],
   "x_label": "Condition", "y_label": "Viability (%)",
   "series": [{"name": "viability", "x": [0, 1], "y": [100, 42],
    "x_labels": ["control", "staurosporine 5 uM"],
    "source": {"locator": "viability.csv",
               "quote": "Cell viability decreased from 100% to 42% after treatment, measured by CCK-8 assay",
               "data_ref": {"file": "viability.csv"}}}]}]}
```

## Expected output (verified on matplotlib 3.11)

- `check_spec.py`: `gate: PASS`, 0 findings.
- `render_spec.py`: SVG (named groups `node_drug`, `edge_drug_apop`, …,
  text as `<text>`), PNG 2160×960 px at 300 dpi, PDF.
- A deliberately corrupted spec (`"y": [100, 37]`) fails the gate with
  `S3 number '37' ... not found in its quote or data_ref`.

## Negative demonstration

Changing any quoted character (e.g. `5 uM` → `5 μM` without the source
saying so) makes check_spec.py exit 1 — the figure cannot be rendered until
the label matches the source or the change is dispositioned in writing.
