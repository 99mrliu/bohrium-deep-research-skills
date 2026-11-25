---
name: semantic-reaction-network
description: Build and audit source-grounded scientific semantic topology for biological mechanisms, apparatus, measurements, and experimental/technical routes. Use when a task requires a typed compartment/entity/process/interaction graph, correct activation versus inhibition, explicit feedback and phases, real CSV chart mappings, source-preserving SVG edits, or comparison of an edited figure with primary figure03 semantics rather than pixel similarity.
---

# Semantic Reaction Network

## Scope and non-negotiable principle

Produce a **typed semantic graph first** and a compact layered SVG second. The graph is the scientific artifact; coordinates and styling are not evidence. This is not a generic JSON-to-SVG converter: every required node and every edge must be supported by a source locator and must pass ontology, topology, source-comparison, and data-mapping audits.

Use for biological mechanisms, assays, experimental apparatus, validation/measurement pipelines, and phase-based technical routes. Use `references/ontology.md` and `references/schema.md` before authoring. Do not infer a plausible mechanism, hidden intermediate, regulatory sign, branch condition, direction, compartment transfer, feedback loop, or causal relation from appearance alone.

## Runtime contract

At evaluation, read the **actual** `/input/case.json` and task statement (`/input/task.md`; if the platform uses `/task.md`, read that). Also inspect supplied files named by the case rather than trusting these paths as content assumptions. For local use, substitute the provided case/input directory. Work in `/app/work`; deliver all actual final artifacts and reports in `/app/output`.

- Do not use bundled synthetic fixtures as official inputs or prepared answers.
- Preserve the original input `case_id` and all original `output_contract` keys as **top-level** keys in `/app/output/result.json`.
- Also include top-level `status` (`success`, `partial`, or `failed`), `sources`, `uncertainties`, `change_records`, and `paths`.
- Hash and locate sources where possible. Never invent source versions, model traces, benchmark scores, measurements, or software/export success.
- The execution limits are 64 model requests and 900 seconds total. Use at most **two semantic review rounds after the initial extraction**: round 1 correct source/ontology/topology defects; round 2 recheck the corrected topology and rendered semantic attributes. Spend remaining effort only on concrete delivery defects.
- Establish an honest `/app/output/result.json` and validation report early (checkpoint `partial`) and improve them incrementally. Missing primary material means `partial`, never fabricated certainty. Fatal semantic errors are `failed` and the renderer exits nonzero.

See `references/runtime.md` for result/checkpoint requirements.

## Mandatory source-first procedure

1. **Resolve the workorder.** Read case JSON and task text, identify required panels, output formats, target edits, and chart requirements. Copy exact contract key names into a work checklist. Inventory the real input files.
2. **Open primary biology before graphing.** For a primary-biological task, locate and actually open the real **figure03** (not a filename-only proxy), read its full caption and relevant methods, and inspect labels, compartments, endpoints, arrowheads/blunt ends, direction, phases, and feedback. For PDF sources, render/read the actual figure page where needed. Record page/panel/region locators. Read `references/source_audit.md`.
3. **Check what the source does not say.** Caption/methods govern textual interpretation; figure03 governs depicted relationships. Do not turn a flat end into activation, a line association into material flow, a correlation into causality, or enzyme proximity into catalysis. Record unresolved or contradictory evidence in `uncertainties`. Absence of evidence is not a negative mechanism claim.
4. **Extract the typed graph.** Author `/app/work/semantic_graph.json` using the schema. Assign compartments, entity/process/measurement/chart kinds, input/output ports and carriers, direction, interaction kind, phase dependencies, branch/join modes, and feedback flags. Cite source IDs on all required nodes and every edge. The program will not invent missing relationships.
5. **Record original semantics and compare.** In `source_semantics`, transcribe the original required node identities/kinds/compartments and exact edge IDs/kind/from/to/feedback plus phase dependencies. In `source_review`, record that actual figure03/caption/methods were inspected and their paths/locators. The comparison must show semantic correspondence between original and final; rearranging the layout is acceptable. See `references/source_audit.md`.
6. **Bind real charts to real data.** Use actual CSV headers and rows, exact x/y/series mappings, source hashes, row counts, units in labels, and an incoming measurement/data relationship. Do not synthesize chart coordinates or silently aggregate/filter/impute rows. If task-supplied CSV is unavailable, report partial instead of making a plausible line chart.
7. **Validate before rendering.** Run `scripts/srn.py` (below). Fix all semantic errors. A generic arrow for activation/inhibition, incompatible endpoints/ports, undeclared cycles, undeclared branch/joins, disconnected required nodes, unsupported mechanisms, or bad CSV mappings blocks the final SVG.
8. **Render, export, and inspect semantics again.** Produce real SVG plus every requested PNG/PDF (using available optional exporters; never install packages). Open the rendered PNG and requested PDF; compare them to original figure03's semantic relationships and source-review record—not pixels. Check compartment membership, labels, ports, material direction, catalysis, activation `+`/open head, inhibition blunt bar, measurement/data path, feedback labels, phase sequence, branch/joins, and chart series. Check clipping and legibility only after semantics.
9. **Edit without rebuilding an existing SVG.** When the workorder requests an edit to provided artwork, preserve the original and apply a targeted exact-once XML patch with `scripts/patch_svg.py`. Do not regenerate the full SVG, normalize it, or replace unmodified IDs/styles. Follow `references/editing.md` and emit an edit audit/change record.
10. **Finalize honestly.** Refresh SVG, semantic graph, validation report, source comparison, requested exports/previews, `export_report.json`, result JSON, sources, uncertainties, and change records. Confirm top-level contract fields and readable paths. A visually polished figure does not upgrade `partial` evidence status.

## Commands

Run from the installed skill root. Python 3 standard library only; no install is needed.

```bash
# Author the source-grounded graph in /app/work first.
PYTHONDONTWRITEBYTECODE=1 python3 scripts/srn.py \
  --graph /app/work/semantic_graph.json \
  --output-dir /app/output \
  --preview-png /app/output/figure.png \
  --preview-pdf /app/output/figure.pdf

# Runnable synthetic demonstration only (not official material).
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_example.py \
  --example-dir examples/synthetic \
  --output-dir /app/output/synthetic \
  --preview-png /app/output/synthetic/figure.png \
  --preview-pdf /app/output/synthetic/figure.pdf

# Negative controls return success only when invalid semantics are rejected.
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_negative.py \
  --example-dir examples/synthetic \
  --report /app/work/negative-test.json

# Structural export and arbitrary-contract regressions.
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_exports.py \
  --example-dir examples/synthetic \
  --report /app/work/export-test.json
```

PNG/PDF export detects `rsvg-convert`, Inkscape, ImageMagick, Chrome/Chromium (including conventional macOS/Windows application paths), and macOS `qlmanage` for PNG. `--preview-pdf` is optional; conventional `output_contract.export_pdf` (or `preview_pdf`) requests PDF export even without that flag, as does any other string contract path ending in `.pdf`. Every requested PDF is actually exported and must pass `%PDF-` signature, page-object, and terminal-EOF checks. PNG signature/IEND is also checked. Exporters write fresh temporary files, so stale or malformed files cannot be reported as success.

`export_report.json` under the output directory records detected tools, attempts, output paths, and structural checks. If no installed exporter succeeds, preserve the editable SVG and validation graph, set the affected contract value to null, return `partial`, and identify the failure; never create a placeholder or claim success. Do not install anything during the case.

## Validation semantics

Read `references/validation.md` for details. In brief:

- material flow/transport use material ports; transport crosses compartments;
- sequence connects process/measurement steps with control ports;
- catalysis starts only at an enzyme/catalyst entity and ends at a process;
- activation/inhibition are regulatory semantics with signal ports and visibly distinct markers, never generic arrows;
- measurement connects observed biology/processes to readouts/charts with data ports;
- directed cycles must be broken by explicit evidence-backed `feedback: true`; a feedback flag outside a cycle is an error;
- required nodes must belong to one connected semantic component;
- material/sequence fan-in/fan-out must have exact all/any/xor join/branch declarations, and XOR alternatives need conditions;
- phase dependencies must be acyclic and sourced;
- every chart series comes directly from the declared CSV, with numeric mapped cells and no substitute data.

Layer IDs in output SVG are stable: background, compartments, entities, processes, measurements, charts, interactions, annotations, and legend. Edge groups retain `data-kind`, `data-from`, `data-to`, `data-feedback`, and `data-source-refs`; chart points retain CSV line/value mappings.

## Failure handling and stopping rules

Stop rendering on semantic errors; the CLI returns 1. Parsing/I/O failures return 2. Successful semantic construction returns 0, although `result.json` may honestly be `partial` because primary material or requested exports are missing.

Use `failed` for unresolved semantic validation errors, `partial` for incomplete input evidence/comparison/export, and `success` only when required evidence, comparison, validation, and exports are complete. Preserve usable partial artifacts and enumerate missing items. Never resolve a warning by inventing science. Do not exceed two semantic review rounds merely to improve appearance.
