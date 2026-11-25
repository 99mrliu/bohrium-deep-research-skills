---
name: compartment-topology
description: Constraint-solve and audit directed cellular pathway topology, receptor/membrane placement, DAG layers, branches, feedback, and legal transport; export or ID-edit source-preserving SVG with real PNG/PDF.
---

# Compartment topology

Use this skill when the scientific task is about **pathway direction, compartment/membrane localization, transport legality, branch hierarchy, or feedback routing**. This is not a general graph beautifier. Its layout coordinates and SVG routes are derived from `compartments`, `entities`, `edges`, and `constraints`; an invalid receptor or transport is an error, not a styling choice.

## Formal run contract

Run with the real case mounted at `/input`; never substitute bundled examples for missing formal inputs.

```bash
python3 /skills/weekly-skill/scripts/run.py \
  --input /input --work /app/work --output /app/output
```

`/input/case.json` and non-empty `/input/task.md` are mandatory. Do not alter authoritative input: stage copies under `/app/work/staged`, add the case-derived topology and normalized workorder there, preserve original `case_id` and `output_contract`, then use `--input /app/work/staged`. Read the actual paper, figure03, caption, body, and data before writing topology. `case.json` supplies `case_id`, `topology` (default `topology.json`), and `workorder` (default `workorder.json`). Relative paths resolve against `/input`. Optional `source_svg`/`figure03` or `source_pdf`/`original_pdf` and zero-based `source_page` identify a source figure. A PDF page is converted to SVG in `/app/work` by PyMuPDF before ID-scoped edits. No network access is used.

The workorder must contain an `output_contract` object and may contain `operations`. `output_contract.artifacts` maps logical artifact names to safe relative filenames; `required_files` lists required filenames. Standard logical names are `layout`, `svg`, `png`, `pdf`, `audit`, `sources`, `uncertainty`, `change_records`, and `result`. See [references/contracts.md](references/contracts.md).

`result.json` retains **every output_contract field**, embeds the full `output_contract`, and dynamically adds the actual `case_id`, `status`, `partial`, `editable_source`, `export_artifact`, `content_map`, `compliance_checks`, `exceptions`, `sources`, `uncertainty`, `change_records`, generated files, per-artifact hashes/format checks, and errors. Success is exit 0. Missing/invalid input, audit failure, missing output, or render failure is non-zero (normally 2), with `status: "partial"` and any artifacts that were actually completed. A partial result is never reported as success.

## Layout guarantees

1. Compartments form horizontal bands in strict `extracellular → membrane → cytosol → nucleus` order.
2. Every `kind: receptor` must belong to the membrane compartment; its node center is exactly on the membrane midline. A receptor in the nucleus exits non-zero.
3. Declared feedback edges and automatically detected DFS back edges are removed before topological sorting. The remaining graph must be a DAG.
4. Longest-path depth assigns layers. A longest source-to-sink chain is selected as the main path; non-main DAG edges are branches. Nodes at the same `(compartment, layer)` are vertically expanded to avoid collisions.
5. Main/branch/transport routes run left-to-right. Feedback is dashed and routed on the outside-right lane. Transport must cross two different, explicitly legal compartments.
6. The audit checks compartment containment, receptor midline alignment, collisions, DAG direction, legal transport, and feedback routing. `layout.json` contains exact node boxes, layer values, routes, main path, and feedback detection reasons.

The SVG has real `<text>` elements and stable IDs (`entity-*`, `edge-*`, `label-*`, `shape-*`, etc.). PNG and PDF are rendered from that SVG using PyMuPDF; they are not placeholder signatures. Inspect the PNG for label clipping, ambiguous arrows, route crossings, and compartment placement before reporting success.

## Source-preserving edits

Set `case.mode: "edit"` and provide the original SVG or PDF. A workorder must explicitly declare human-readable `changed` and `unchanged` scopes:

```json
{
  "changed": ["label-REC text", "shape-REC fill"],
  "unchanged": ["All other SVG elements and all unlisted topology fields"],
  "operations": [
    {"op": "update_svg_text", "id": "label-REC", "text": "Edited receptor"},
    {"op": "update_svg_attr", "id": "shape-REC", "name": "fill", "value": "#ffd166"}
  ],
  "output_contract": {"required_files": ["layout.json", "figure.svg", "figure.png", "figure.pdf", "result.json"]}
}
```

`update_svg_text` only edits a text/tspan/title/desc element with the exact ID. `update_svg_attr` only edits that exact ID and rejects event handlers and external references. Untargeted subtrees are compared before/after. With no SVG operation, source bytes are copied exactly. Every operation is logged with before/after and changed/unchanged scope in `change_records.json`.

Topology operations (`set_entity_compartment`, `update_label`, `set_entity_kind`, `set_edge_kind`, `set_feedback`, `set_constraint`) update topology and recompute `layout.json`. On a preserved source figure, **geometry is not silently synchronized**: use explicit `update_svg_attr` operations for intended visual changes. The runner records a `PRESERVED_GEOMETRY` uncertainty when topology edits accompany a source-preserving visual edit. For a full relayout, run create mode without a source SVG instead.

## Reference and synthetic smoke test

Read [references/input_schema.md](references/input_schema.md) for the full schema and [references/contracts.md](references/contracts.md) for output/error details. Everything under `examples/SYNTHETIC/` is fabricated solely for testing, including its labels. It contains branch, feedback, and transport, and is never a fallback input.

A local staging equivalent (paths outside the bundle, adapted to the current challenge root) is:

```bash
python3 bundles/compartment-topology/scripts/run.py \
  --input validation/compartment-topology/create/input \
  --work validation/compartment-topology/create/work \
  --output validation/compartment-topology/create/output
```

Dependencies: Python 3.10+ and PyMuPDF (`import pymupdf`). The core constraint solver and SVG writer otherwise use the standard library.
