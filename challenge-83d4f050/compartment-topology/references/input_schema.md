# Input schema

All identifiers are non-empty, unique strings within their category. All JSON must be UTF-8; JSON NaN/Infinity are rejected by the writer and non-finite layout dimensions are rejected by the solver.

## `case.json`

Required: `case_id`. Optional: `mode` (`create` or `edit`), `topology`, `workorder`, `source_svg` (alias `figure03`), `source_pdf` (alias `original_pdf`), `source_page`, and `synthetic`. Edit mode requires an SVG or PDF source. The runner does not infer or fetch missing data.

## `topology.json`

Top-level arrays/objects `compartments`, `entities`, `edges`, and `constraints` are all required.

```json
{
  "compartments": [
    {"id": "outside", "role": "extracellular", "order": 0, "label": "Extracellular"},
    {"id": "pm", "role": "membrane", "order": 1, "label": "Plasma membrane"},
    {"id": "cyto", "role": "cytosol", "order": 2, "label": "Cytosol"},
    {"id": "nuc", "role": "nucleus", "order": 3, "label": "Nucleus"}
  ],
  "entities": [
    {"id": "REC", "label": "Receptor", "kind": "receptor", "compartment": "pm"}
  ],
  "edges": [
    {"id": "E1", "source": "REC", "target": "OTHER", "kind": "activation"}
  ],
  "constraints": {
    "canvas": {"width": 1400, "height": 900},
    "layer_gap": 220,
    "margin_x": 100,
    "feedback_edges": [],
    "allowed_transitions": [["cytosol", "nucleus"]]
  }
}
```

Exactly one compartment per role is required and integer order values must produce the stated role sequence. `kind` defaults to `molecule`; `label` defaults to entity ID. Receptor compartment is membrane only. Edge kind defaults to `activation`; source and target must exist.

Transport checks the source/target compartment roles. Same-compartment transport is invalid. If `allowed_transitions` is omitted, the default directional set is extracellular↔membrane, membrane↔cytosol, extracellular↔cytosol, and cytosol↔nucleus. A supplied array replaces that default; entries can be `[from,to]` or `{ "from": ..., "to": ... }`. This only validates compartment transitions, not biological evidence for a mechanism.

Feedback edge IDs must exist. Cycles not covered by declarations are detected as DFS back edges in deterministic entity/edge order; automatic classification is reported in `layout.feedback_edges` and should be reviewed scientifically. The remaining non-feedback graph must be a DAG.

## Workorder topology operations

- `set_entity_compartment`: `id`, `compartment`
- `update_label`: `id`, `label`
- `set_entity_kind`: `id`, `kind`
- `set_edge_kind`: `id`, `kind`
- `set_feedback`: edge `id`, boolean `feedback`
- `set_constraint`: existing dotted `path` beginning `constraints.`, `value`; optional `id` for audit linkage

SVG operations are `update_svg_text` (`id`, `text`) and `update_svg_attr` (`id`, `name`, `value`). No operation silently targets the closest label or an entire class. Unknown IDs, unknown operations, unchanged constraint assignments, and invalid post-edit topology fail non-zero.

## Limitations

The solver detects cycles, not biological sign or causality. Main-path ties use entity input order. Equal-compartment/layer nodes are spread vertically; general edge-crossing minimization, arbitrary compartment geometries, and semantic reconciliation of a pre-existing drawing with new topology are not claimed. Source PDF extraction depends on the PDF containing usable vector/text content; scanned pages may produce unhelpful source geometry and should be inspected.
