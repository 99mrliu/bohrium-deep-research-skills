# Archetype params reference (Bundle B)

Common fields (all archetypes):

```json
{"title": "headline", "subtitle": "optional one-liner",
 "canvas": {"w": 691, "h": 384},
 "sources": [{"locator": "material.txt line 1", "quote": "verbatim"}],
 "legend": [{"color_token": "process", "label": "fabrication step"}]}
```

- Canvas default 691×384 px = 7.2×4.0 in at 96 px/in. Keep height ≥ 320 px
  for `hub-mechanism` (orbit needs room; the builder shrinks the hub rather
  than letting shapes collide, but labels still need space).
- `legend` items use tokens from `style_tokens.md`.
- Text auto-fitting: hub labels shrink (≥ 8 px) to fit the hub; everything
  else is checked, not shrunk — if the audit flags it, shorten the text.

## linear-pipeline

```json
{"stages": [{"label": ["Perovskite", "precursor"], "role": "entity",
             "sublabel": ["optional detail"]}],
 "edges": [{"label": "step 1"}]}
```
- 2–5 stages; `edges` has len(stages)−1 entries (labels may be null).
- Roles: entity/process/condition/outcome/intervention (fill by role).

## hub-mechanism

```json
{"center": {"label": ["HeLa cells"]},
 "satellites": [{"label": ["Caspase-3", "activation"], "role": "process",
                 "angle_deg": 60, "edge": "out", "edge_label": "optional",
                 "inhibit": false}]}
```
- 3–6 satellites. `edge: "in"` (acts on hub) or `"out"` (consequence).
  `inhibit: true` draws a blunt bar instead of an arrowhead.
- `angle_deg`: 0 = right, 90 = down, 180 = left, 270/-90 = up.

## compare-split

```json
{"left":  {"heading": "Control", "items": [{"label": ["Viability 100%"],
            "role": "control"}], "stats": ["n = 3 replicates"]},
 "right": {"heading": "Treated", "items": [{"label": ["Viability 42%"],
            "role": "outcome"}], "stats": ["Annexin V positive"]},
 "transition": "5 uM staurosporine",
 "verdict": "Viability drops to 42%"}
```
- `items` stack vertically (≤ 4 per side); `stats` are small print under
  them; `verdict` is the bold bottom line (the conclusion — anchor it).

## layered-stack

```json
{"layers": [{"label": ["Perovskite"], "role": "entity", "fill": "accent",
             "thickness": 1.4, "note": "500 nm absorber"}],
 "scale_bar": {"px": 60, "label": "not to scale"}}
```
- Top-to-bottom = source order. `thickness` is relative. `note` becomes a
  leader-line annotation on the right. Dark fills get white text
  automatically (luminance check).

## data-panel

```json
{"charts": [{"kind": "bar", "title": "Viability", "y_label": "Viability (%)",
             "x_labels": ["ctrl", "STS"],
             "series": [{"name": "viability", "values": [100, 42],
                         "color_token": "accent"}]}]}
```
- 1–3 charts in a row; `kind: "bar" | "line"`. Values must be literally
  present in the quoted source / data file (the forge's anchor check covers
  `sources[]`; you must keep numbers consistent — canvas_audit does not
  re-check numerics).
- Multi-series entries across all charts feed the shared legend strip.
