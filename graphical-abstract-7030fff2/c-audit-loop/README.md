# ga-audit-loop (Bundle C)

**One-line:** no figure ships until every element has a verbatim source
citation, the SVG passes a named defect scan, and any edit of a provided
figure is a byte-preserving patch with a diff record.

## Why this direction

The failures that sink graphical abstracts in real workflows are not
"cannot draw" but "cannot be checked": orphan numbers, quotes that drifted,
raster-only deliverables, and edits that silently redraw everything. This
skill is drawing-agnostic — it wraps ANY figure production in three machine
gates (source ledger, defect scan, patch+pixel-diff) so the deliverable is
auditable pixel by pixel. It shares no code with spec-compiler or
archetype-forge approaches.

## Contents

| File | Role |
|---|---|
| `SKILL.md` | protocol, edit-mode rules, failure handling |
| `scripts/mine_sources.py` | materials → `evidence_pool.jsonl` (stable `file#page-N` keys) + `number_index.json` + sha256 report |
| `scripts/ledger_verify.py` | blocking gate: verbatim quotes, number tracing, two-way SVG coverage |
| `scripts/svg_inspect.py` | defect scan for ANY SVG (D-OVERFLOW/D-FONTMIN/D-CLIP/D-VIEWBOX/D-NOLAYER/D-RASTER/D-EMPTYTXT) |
| `scripts/apply_patch.py` | source-preserving SVG edit: exact-once ops, unified-diff change record |
| `scripts/render_diff.py` | rasterise via exporter chain; pixel-diff before/after PNGs (numpy via matplotlib) |
| `scripts/finalize_result.py` | early-partial + phased result.json writer |
| `references/ledger_format.md` | ledger grammar + verification semantics |
| `references/defect_taxonomy.md` | defect codes + repair moves |
| `examples/minimal_example.md` | runnable demo incl. failing-ledger case (marked as example) |

## Dependencies

Python 3.9+; matplotlib (for PNG reading in render_diff); pdftotext for PDF
mining; rsvg-convert/inkscape/soffice optional for rasterisation. No network.

## Usage

See `SKILL.md` §Protocol. Works in two modes: **new figure** (mine → draw →
ledger gate → defect scan → export) and **edit mode** (inspect starting
figure → minimal patch → diff proof → export).

## Self-verification performed by the author

- Good ledger passes; fabricated `37%` value fails with `orphan-number`;
  wrong pool key fails with `bad-locator`.
- Inspector CLEAN on five independently built SVGs; caught a real
  multi-line-tspan measurement bug during development (fixed before
  shipping).
- Patch applied 1 op, 1 diff hunk, 2 changed lines; everything else
  byte-identical. Identity pixel-diff reports 0.0 changed fraction.

## Maintenance

Adding a defect code = one check in `svg_inspect.py` + one row in
`references/defect_taxonomy.md`. Issues via the GitHub repo in
`GITHUB_URL.txt`.
