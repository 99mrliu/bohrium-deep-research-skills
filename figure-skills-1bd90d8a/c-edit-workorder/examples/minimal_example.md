# Minimal worked example (示例 / illustrative only)

Everything below uses **synthetic** data invented for documentation. It is not
an answer to any official case. Commands assume `$SKILL_DIR` points at this
skill directory and work happens under `/app/work`, deliverables under
`/app/output`.

## 1. Synthetic source data — `/app/work/data.csv`

```csv
group,ctrl,drug,ctrl_err,drug_err
A,1.2,2.4,0.1,0.2
B,2.0,3.1,0.15,0.25
C,1.5,2.8,0.12,0.18
```

## 2. Compose plan — `/app/work/plan.json`

```json
{"mode": "chart", "chart_type": "bar", "title": "Response rate",
 "x_label": "Group", "y_label": "Rate (a.u.)",
 "width_mm": 120, "height_mm": 80, "categories": ["A", "B", "C"],
 "series": [
  {"name": "ctrl", "x": ["A", "B", "C"], "y": [1.2, 2.0, 1.5],
   "yerr": [0.1, 0.15, 0.12],
   "source": "data.csv", "source_locator": "data.csv#column=ctrl"},
  {"name": "drug", "x": ["A", "B", "C"], "y": [2.4, 3.1, 2.8],
   "yerr": [0.2, 0.25, 0.18],
   "source": "data.csv", "source_locator": "data.csv#column=drug"}]}
```

## 3. Compose (GENERATE mode)

```bash
python3 $SKILL_DIR/scripts/compose_svg.py /app/work/plan.json \
  --out-svg /app/work/figure.svg --figmap /app/work/figmap.json
# -> wrote ... (mode=chart, calibrated=True, series=2)
```

Every bar is `<g id="series/drug/bar-1">…`; the figmap records
`axes.y = {a: -48.0…, b: 188.77…}` fitted from the actual SVG geometry, so
`svg_y = a*value + b` exactly (verified: bar `drug/B` top == `a*3.1+b` to
4 decimals).

## 4. Workorder — `/app/work/workorder.json` (4 applied ops + 1 rejected)

```json
{"ops": [
 {"op": "update_value", "series": "drug", "key": "B", "value": 3.6,
  "source_ref": "data.csv#column=drug,row=B"},
 {"op": "restyle_series", "series": "ctrl", "color": "#009E73"},
 {"op": "relabel", "target_id": "label/title",
  "new_text": "Response rate (revised)"},
 {"op": "add_annotation", "id": "sig1", "x_data": "B", "y_data": 3.6,
  "text": "p<0.05", "source_ref": "paper.pdf#page=3,fig2"},
 {"op": "update_value", "series": "ctrl", "key": "A", "value": 9.9}
]}
```

```bash
python3 $SKILL_DIR/scripts/apply_workorder.py /app/work/figure.svg \
  /app/work/workorder.json --figmap /app/work/figmap.json \
  --out-svg /app/output/figure.svg --log /app/output/change_log.json
# op 1 update_value  -> applied (warning: yerr geometry NOT re-derived)
# op 2 restyle_series -> applied
# op 3 relabel        -> applied
# op 4 add_annotation -> applied
# op 5 update_value   -> rejected: update_value requires source_ref
# applied=4 rejected=1 -> exit 0
```

After op 1 the bar `series/drug/bar-1` top pixel equals `a*3.6+b` to 4
decimals — geometry came from the data, not from hand-computed pixels.

## 5. change_log.json excerpt (old/new/source_ref)

```json
{"seq": 1, "op": "update_value", "target": "drug",
 "source_ref": "data.csv#column=drug,row=B",
 "status": "applied", "old": 3.1, "new": 3.6,
 "detail": "warning: yerr geometry NOT re-derived; verify error bars"}
{"seq": 3, "op": "relabel", "target": "label/title",
 "status": "applied", "old": "Response rate", "new": "Response rate (revised)"}
{"seq": 5, "op": "update_value", "target": "ctrl", "source_ref": null,
 "status": "rejected",
 "detail": "update_value requires source_ref (or manual:true + reason)"}
```

A *manual* correction is possible but conspicuous:

```json
{"op": "update_value", "series": "ctrl", "index": 2, "value": 1.7,
 "manual": true, "reason": "typo fix confirmed by PI email 2026-11-20"}
```
→ applied, and the log entry ends with `人工修改 manual edit: typo fix …`.

## 6. Export + compliance

```bash
python3 $SKILL_DIR/scripts/export_journal.py /app/output/figure.svg \
  --preset nature_double --out-dir /app/output \
  --report /app/output/export_report.json
python3 $SKILL_DIR/scripts/export_check.py /app/output/figure.svg \
  /app/output/figure.pdf /app/output/figure.png \
  --preset nature_double --report /app/output/export_check.json
```

Typical export_check summary (composed at 120 mm, exported to 183 mm):

```
svg_width_mm   pass  183.00 mm vs preset 183.00 mm
editable_text  pass  18 <text> elements present (23 paths)
font_family    pass  families with fallbacks present
font_floor     warn  sizes outside [5, 7] pt: [9.15, 10.68, ...]   <- upscale!
background     warn  no full-canvas background rect (likely transparent)
png_dpi        pass  300 dpi >= preset 300
```

The `font_floor` warning is the preset system working as intended: compose at
the target width (`"width_mm": 183` in the plan) to keep 7 pt text 7 pt.

## Mini-example: rejected op, honest by construction

Op 5 above (`"value": 9.9` with no `source_ref`) was **rejected** and the SVG
was left untouched for that bar. To make it pass legitimately you either point
at a real source cell or own the edit manually with `manual:true + reason` —
either way the change log tells the truth.
