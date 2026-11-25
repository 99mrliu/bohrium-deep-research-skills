---
name: vector-publication-studio
description: Build and surgically edit source-faithful scientific apparatus, mechanism, route, and CSV chart figures as deterministic editable SVG with automatic lane routing, accessible redundant encodings, provenance, and verified PNG/PDF export. Use for experimental apparatus, technical routes, biological activation/inhibition diagrams, figure03 revisions, CSV chart panels, source-preserving SVG edits, and publication QC.
---

# Vector Publication Studio

Produce a publication-ready **editable SVG and its reproducible source**, not merely a raster depiction. Preserve scientific meaning first; then optimize layout and export. This Skill includes apparatus glyphs, DAG/lane layout with collision-aware orthogonal routing, native SVG text/groups/IDs, activation-arrow versus inhibition-bar semantics, CSV column/value mapping, byte-span SVG patching, and real export checks. Chart requests are supported, never dismissed as out of scope.

## Non-negotiable evidence rule

The actual `case.json`, actual `task.md`, supplied paper/PDF, supplied figures, and CSV/data files are the only factual basis. **Inspect the original paper and original `figure03` whenever available, including its caption, methods, labels, spatial connections, arrowheads, inhibition bars, numbers, units, and nearby text.** Compare the candidate output entity-by-entity and relationship-by-relationship against those originals. Do not infer a scientific entity, pathway, mechanism, number, connection, or direction from a file name, a domain label, a common textbook pathway, or visual plausibility. Do not copy a synthetic example into an actual result.

Distinguish: (1) directly supported by a source; (2) layout-only interpretation; (3) unresolved ambiguity. If a relation is ambiguous, omit the relation or depict a clearly labelled non-directional unresolved connector in a separate note—not an invented arrow—and report an uncertainty. Sources support the figure but are not a substitute for careful reading.

## Runtime and output contract (mandatory)

At evaluation time read the actual `/input/case.json`; read the task from `/input/task.md` or `/task.md`, passing the path that actually exists to the runner. Locate and inspect all supplied material under `/input`. Work only under `/app/work`. Put final/reports in `/app/output`.

1. Read `case_id` and every key in `output_contract`. Every such key must occur **at top level** of `/app/output/result.json`; do not hide contract fields inside a nested `artifacts` object. Also keep top-level `case_id`.
2. Save honest partial work early. A partial/failed result must enumerate missing material, export limits, unverified regions, and unresolved contract fields. Missing input, scientific ambiguity, and runtime/export failure are different states.
3. Include source/version locators, uncertainties, data mappings, and change records. Do not fabricate font embedding, installed software, successful export, scientific agreement, reviews, or benchmark scores.
4. Runtime tools may be absent. Core generation requires only Python 3 stdlib; optional export tools are detected and no installation is attempted. CairoSVG, `rsvg-convert`, Inkscape, or Chrome may be used if genuinely present. The exporter attempts CairoSVG, `rsvg-convert`, Inkscape, then Chrome Headless until one genuinely succeeds; all attempts/failures and the actual selected tool are reported.
5. Keep live SVG text editable. The builder does **not** embed fonts. Disclose this and inspect CJK/font substitution in the actual preview. If a separately verified workflow embeds fonts, say precisely how it was verified; otherwise `font_embedding` remains false.
6. Recommended top-level fields (in addition to every original contract key): `status`, `editable_source`, `source_spec`, `exports`, `export_qc_report`, `sources`, `uncertainties`, `change_records`, `data_mappings`, `routes`, and `font_embedding`.

Use `scripts/run_case.py` after authoring `/app/work/source_spec.json`:

```bash
python3 scripts/run_case.py \
  --case /input/case.json --task /input/task.md \
  --spec /app/work/source_spec.json --output-dir /app/output
```

The runner writes `figure.svg`, `source_spec.json`, copied source CSV(s), `layout_manifest.json`, real `figure.png` and `figure.pdf`, `export_qc.json`, and `result.json`. It returns nonzero on build/export failure and code 3 for an honest partial (for example, missing source evidence). Inspect unmapped original contract fields and correct them explicitly before finalizing. If export is unavailable, `--skip-export` still leaves a useful editable SVG, but the omission must be reported.

## Source-first workflow

### 1. Inventory and inspect before drawing

- Save an inventory in `/app/work`: filenames, file hashes if useful, page/figure identifiers, data-file columns, and task requirements.
- Parse/read the actual PDF. Render original `figure03` at sufficient resolution and visually inspect it; extracted text alone is insufficient for connectors. Also inspect the paper caption and relevant methods/results text.
- Create an entity ledger: stable ID, exact source label, type, qualitative/quantitative attributes, source page/panel/region.
- Create a relationship ledger: source ID, target ID, relation semantics, direction, line style in original, source locator, confidence/ambiguity. Compare each output arrow/bar back to this ledger.
- Create a chart ledger: CSV header, selected x/y columns, units, valid row counts, missing/nonfinite values, transformation (none unless specifically needed and disclosed), and ranges derived from actual values.
- If editing supplied SVG/PDF artwork, identify whether actual editable vector source exists. A rebuilt lookalike is a new reconstruction, never a source-preserving edit.

### 2. Author `source_spec.json`

Copy `examples/synthetic/input/source_spec.json` only as a schema/template. Set `synthetic: false`, replace all sample entities/data/sources, and use actual task wording. Detailed schema: `references/source-spec.md`.

Important fields:

- `canvas`: viewBox width/height plus physical width/height in millimetres.
- `nodes`: unique `id`, exact source-faithful `label`, apparatus `kind`, optional `rank`, `lane`, `sublabel`, `sources`.
- `edges`: unique `id`, `from`, `to`, `kind`, optional source-faithful short `label`, `sources`.
- `charts`: actual `data_csv`, exact `x_column`, `y_columns`, axis labels/units, and panel box.
- `sources`: paper/page/figure/caption/CSV row-column locators.
- `change_records`: new reconstruction versus addressed source-preserving patches, including reviewer/confirmation status if known.

Automatic ranking uses process/material edges and ignores `information` feedback for topological ranks. Explicit `rank` and `lane` are preferred when the original has a known spatial layout. Give every rank/lane slot at most one node. Cyclic process routes need a clearly identified feedback edge or explicit ranks. Router output, including bends and endpoints, is saved in `layout_manifest.json` for review.

### 3. Build and inspect

```bash
python3 scripts/studio.py build \
  --spec /app/work/source_spec.json --output-dir /app/work/build
python3 scripts/studio.py export \
  --svg /app/work/build/figure.svg --output-dir /app/work/build \
  --png /app/work/build/figure.png --pdf /app/work/build/figure.pdf \
  --report /app/work/build/export_qc.json
```

Inspect the rendered PNG, not just XML. Spend **at most two visual review rounds**. In each round check:

- entity names/counts against the original paper and figure03;
- every connection and direction, especially reverse feedback and split/join paths;
- activation uses an arrowhead and activation wording; inhibition uses a terminal perpendicular bar and inhibition wording—**never an arrowhead**;
- no unintended endpoint, disconnected route, node collision, clipped label, panel overflow, confusing bend, or false tee/junction;
- color is redundant with dash/marker: material solid blue, energy dashed orange, information dotted purple, activation solid green arrow, inhibition solid red bar. Legends are generated only from relation kinds actually present;
- CSV lines, points, ticks, and values agree with exact source columns and units;
- physical dimensions/viewBox, legibility at final size, visible font substitution, contrast, and source/uncertainty notes.

If a visual or scientific defect exists, change the source spec or address an exact SVG node; do not cover it with a raster or cosmetically hide it. Record the change.

### 4. Existing SVG edits: preserve the original bytes

Use `scripts/patch_svg.py` for an existing SVG. It uses Expat byte offsets and edits only addressed text or attribute spans. It does not prettify or reserialize the XML; comments, whitespace, namespace declarations, and all non-addressed nodes remain byte-identical. It refuses missing/duplicate IDs, mixed-content text edits, invalid XML, and unsafe attribute names.

```bash
python3 scripts/patch_svg.py \
  --input /app/work/original.svg --output /app/output/figure-edited.svg \
  --edits /app/work/edits.json --report /app/output/edit_report.json
```

Example `edits.json`:

```json
[
  {"op": "set_text", "id": "figure-title", "text": "Corrected source-faithful title"},
  {"op": "set_attr", "id": "node-pump", "name": "fill", "value": "#F8FAFC"},
  {"op": "remove_attr", "id": "obsolete-highlight", "name": "filter"}
]
```

`set_text` targets simple elements without child elements; target an individual text/tspan node when using generated multi-line text. `id` itself cannot be patched. After editing, verify the SVG and inspect a new preview. For broader geometry changes, reconstruct explicitly and report a rebuild. Never claim byte preservation after full generation.

### 5. Final evidence and QC

Independent checks are in `references/publication-qc.md`. Required result/report behavior:

- SVG parses; IDs are unique; `url(#…)` marker references resolve; groups/layers/live text are present; viewBox and physical width/height are present.
- PNG signature, IHDR dimensions, every chunk CRC, IDAT and IEND are checked. PDF signature, page object, MediaBox and EOF are checked. These are real structural checks, not a claim of scientific correctness.
- PNG/PDF export failures are nonzero, not silently converted to success. No generated binary is bundled with the Skill.
- `layout_manifest.json` exposes node rank/lane, every route's vertices, copied CSV names, and exact chart mappings.
- All critical entities and relationships have source locators or explicit uncertainty. Original-paper agreement requires visual/scientific comparison, not an export pass.

## Failure behavior

Commands exit nonzero for malformed JSON/CSV, unknown/missing columns, nonnumeric or nonfinite data, duplicate IDs/endpoints, unsupported relation/glyph, impossible rank cycle, route collision, label overflow, missing fonts/export tools when export is requested, malformed SVG, or failed export validation. Shorten only redundant wording—never alter scientific meaning—to fix overflow; otherwise enlarge the node/canvas/panel.

If some work can be retained, keep valid source and SVG, write `result.json` with `status: "partial"`, enumerate what is missing, and return an honest partial indicator. If no valid artifact exists, use `failed`. A missing paper cannot be replaced by a guessed pathway; missing numeric data cannot be replaced by invented values.

## Synthetic example

The only bundled example is explicitly **SYNTHETIC** and contains an apparatus/control panel plus a chart from actual bundled CSV columns. Run:

```bash
python3 scripts/run_example.py \
  --example-dir examples/synthetic \
  --output-dir /app/work/synthetic-output \
  --preview-png /app/work/synthetic-output/preview.png --pdf
```

It also creates a separate `figure-edited.svg` using byte-preserving `set_text` and `set_attr`, with `edit_report.json`. Example outputs are demonstrations, never formal case answers. No fonts are embedded. See `examples/synthetic/README.md` and `references/publication-qc.md` for negative-test commands and limitations.
