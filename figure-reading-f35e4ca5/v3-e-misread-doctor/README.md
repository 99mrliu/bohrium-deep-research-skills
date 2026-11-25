# misread-doctor-figure-reading (bundle E)

Diagnose-first playbook for reading scientific figures under a harness budget.
Thesis: misreading clusters into ~12 named failure modes; cheap mechanical
detectors (tick geometry, unit strings, ink topology) identify *which modes are
live in this figure before reading*, and each live mode maps to a concrete repair
recipe plus a post-read self-check. It is a knowledge-and-detection layer, not a
reading pipeline.

## Dependencies

- Python 3 standard library
- `numpy` 2.x
- `PIL` 12.x
- `matplotlib` 3.x — only for `examples/make_synthetic_case.py`
- No network, no pip, no scipy. (Poppler tools are available in the harness for
  PDF figures but are not required by these scripts.)

## Inputs

All scripts consume a **figure card** written by the agent after visual
inspection (`--card figure_card.json`). Schema (full detail in
`references/failure_taxonomy.md`):

```json
{
  "chart_type": "line | bar | scatter | multi-panel: ...",
  "axes": [
    {"id": "top_y", "orientation": "y", "side": "left", "panel": "top",
     "chart_type": "line",
     "label_verbatim": "Potential (mV)", "unit_verbatim": "mV",
     "declared_type": "linear | log | symlog | categorical",
     "ticks": [{"value": 0.001, "pixel": 123.4}, ... (>=3)],
     "range": [0.001, 10]}
  ],
  "legend": [{"name": "...", "color": "...", "marker": "..."}],
  "plot_area_bbox": [x0, y0, x1, y1]   // or {"panel": [x0,y0,x1,y1], ...}
  "element_inventory": [{"type": "bar", "bbox": [...]}, ...],
  "table_units": ["V", "s", ...]
}
```

Pixel coordinates use image convention: origin top-left, y down. `pixel` in a
tick is the coordinate *along* that axis (y-pixel for y axes, x-pixel for x axes).

## Scripts & outputs

| script | CLI | output |
|---|---|---|
| `scripts/detect_axis_geometry.py` | `--card C --work W` | `W/axis_diagnosis.json` — per-axis type verdict, fit residuals, unit parse, flags w/ severity |
| `scripts/detect_nondata_ink.py` | `--image I --card C --work W --out O` | `O` (nondata_elements.json) — candidates `{type, bbox, confidence, action: exclude_from_data}` + `agent_confirm` list |
| `scripts/repair_plan.py` | `--axis-diag A --nondata N --card C --work W --out O` | `O` (repair_plan.json) + `W/misread_report.json` skeleton |

## Exit codes

- `0` — ran clean, **no** live failure modes / candidates found
- `2` — ran clean, **≥1** live failure mode / candidate found (this is a finding,
  not a failure)
- `1` — actual error (bad input, unreadable file, malformed card)

## Limitations

- Heuristics, not proofs: negative detector output never proves a trap is absent;
  positive output requires visual confirmation on the zoomed figure.
- Axis typing needs ≥3 numeric ticks per axis; unit screening needs verbatim unit
  strings; ink heuristics degrade on very dense or low-resolution figures.
- The star/bracket/line detectors work on raster ink only — they cannot see
  semantics, which is why every candidate is mirrored into `agent_confirm`.

## Maintenance

- The failure taxonomy lives in `references/failure_taxonomy.md`; the repair
  cookbook with worked numeric examples in `references/repair_recipes.md`.
  Keep the recipe tables in `scripts/repair_plan.py` in sync when editing those.
- Regenerate the synthetic demo with
  `python3 examples/make_synthetic_case.py --out /tmp/f35e-e-demo` and re-run the
  three scripts end-to-end after any change (see `examples/minimal_example.md`).
- Keep everything UTF-8 text: no binaries, no `__pycache__`, no symlinks in the
  skill directory.
