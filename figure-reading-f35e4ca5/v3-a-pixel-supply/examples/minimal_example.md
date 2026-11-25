# Minimal example (合成示例 — SYNTHETIC demo, not a formal case result)

Everything on this page is produced from **invented, synthetic data** generated
by `make_synthetic_case.py`. The outputs shown are 示意输出 (illustrative
outputs) that demonstrate file shapes and the command sequence; they are **not**
formal case results and must never be cited as such.

## 1. Generate the synthetic case

```
python3 examples/make_synthetic_case.py --out /tmp/f35e-a-demo
# prints: /tmp/f35e-a-demo   (contains case.json, task.md,
#                             figure_synthetic_4panel.png, table_fold_change.csv)
```

The synthetic figure is a 2×2 multi-panel PNG (labels (a)–(d)): (a) line plot
with log-y axis in mV, (b) grouped bars with error bars and significance
stars, (c) scatter with legend, (d) spectrum-like peaks. `case.json` carries
`case_id: "synthetic-demo-A"`, a small mixed-shape `output_contract`, a
materials list, and a declared gap (Figure S1 mentioned but not shipped).

## 2. Run the supply chain (three commands)

```
python3 scripts/supply_images.py --input-dir /tmp/f35e-a-demo \
    --work /tmp/f35e-a-work --out /tmp/f35e-a-out
python3 scripts/tile_panels.py \
    --image /tmp/f35e-a-demo/figure_synthetic_4panel.png \
    --work /tmp/f35e-a-work --out /tmp/f35e-a-out/panels
python3 scripts/zoom_regions.py \
    --image /tmp/f35e-a-demo/figure_synthetic_4panel.png \
    --panels /tmp/f35e-a-out/panels/panels.json --out /tmp/f35e-a-out/zoom
```

Observed exit codes on the synthetic case: `0`, `2`, `0`. The `2` from
`tile_panels.py` is the expected degraded-partial code: it found 4 panels but
could not locate a label cluster for one of them (a warning, not a failure).

## 3. What each output looks like (示意输出 excerpts)

`image_supply.json` — inventory + verdicts:

```json
{
 "case_id": "synthetic-demo-A",
 "inventory": [
  {"path": "/tmp/f35e-a-demo/figure_synthetic_4panel.png", "kind": "image"},
  {"path": "/tmp/f35e-a-demo/table_fold_change.csv", "kind": "table"}
 ],
 "verdicts": {"/tmp/f35e-a-demo/figure_synthetic_4panel.png": ["ok"]},
 "degraded": []
}
```

`panels.json` — 4 panels, bbox in original-image coordinates:

```json
{
 "single_panel": false,
 "n_panels": 4,
 "first_panel": {
  "panel_id": "panel_1",
  "label_guess": "label_cluster@(136,210)-(201,230) glyphs=3",
  "bbox_original": [71, 142, 905, 786],
  "crop_path": "/tmp/f35e-a-out/panels/panel_1.png",
  "scale": 2.0
 }
}
```

`zoom_manifest.json` — 16 tiles (4 panels × 4 regions), each traceable:

```json
{
 "coordinate_note": "orig_xy = bbox_original[:2] + tile_xy / scale",
 "panel_1_bottom_axis.png": {
  "panel": "panel_1", "region": "bottom_axis",
  "bbox_original": [71, 689, 905, 786], "scale": 4.0
 }
}
```

Visually checking the tiles (recommended): `panel_1_left_axis.png` shows the
full log-y tick labels (`3×10⁰`, `6×10⁻¹`, …) and the y title
`membrane potential (mV)`; `panel_1_legend_zone.png` shows the `cell A` /
`cell B` legend; `panel_2_bottom_axis.png` shows the `ctrl` / `drug X` /
`drug Y` tick labels — all legible at 3–4× zoom.

## 4. Reminder

These outputs exist only to prove the supply chain works end to end. On a real
harness case, replace the paths with `/input`, `/app/work`, `/app/output`, and
follow `SKILL.md`'s workflow (partial `result.json` first, honest `status`,
declared gaps listed, every value cited with tile + original-image bbox).
