# Semantic Reaction Network Skill

A Python-standard-library Skill for **source-grounded scientific semantic topology**, especially biological mechanisms, experimental apparatus, assays, measurements, and technical routes. The central artifact is a typed graph—not a generic JSON-to-SVG styling exercise.

## What it adds

- compartments, entity/process/measurement/chart nodes, typed input/output ports;
- material flow, sequence, activation, inhibition, catalysis, transport, and measurement relations;
- source refs, phase dependencies, explicit feedback, branch/join semantics, and uncertainty/change records;
- nonzero exits for incompatible endpoints/ports, generic regulatory arrows, unmarked cycles, false feedback, disconnected required nodes, bad fan-in/fan-out, bad phase cycles, unsupported required semantics, and invalid CSV mappings;
- source-figure semantic comparison independent of pixel layout;
- layered editable SVG with scientific `data-*` semantics;
- optional real PNG/PDF export with Chrome/Chromium and other installed-tool fallbacks, structural output checks, and an export report;
- charts parsed directly from actual CSV headers/rows;
- exact-once targeted SVG XML edits preserving unmodified IDs/styles;
- runtime/result rules for `/input`, `/app/work`, `/app/output`, honest partial checkpoints, and top-level output-contract fields.

Start with `SKILL.md`. Ontology and operational rules are under `references/`; implementation and tests are under `scripts/`.

## No installation

Python 3.10+ standard library is sufficient (tested with Python 3.12). No network or package installation is used. Optional PNG/PDF export autodetects `rsvg-convert`, Inkscape, ImageMagick, and Chrome/Chromium on PATH or in conventional macOS/Windows application locations; macOS `qlmanage` is a PNG-only fallback. No exporter is bundled. If none works, the SVG/graph remain usable and the result is partial with a null affected contract path.

## Runnable SYNTHETIC minimal example

**The bundled enzymatic assay, values, source-like figure03, caption, and methods are entirely SYNTHETIC. They are not official cases, primary biological evidence, real measurements, or prepared answers.** They demonstrate enzyme catalysis, substrate/product material flow, an inhibitor blunt bar, measurement, and a real text CSV mapping.

From the bundle root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_example.py \
  --example-dir examples/synthetic \
  --output-dir /app/output/synthetic \
  --preview-png /app/output/synthetic/synthetic-preview.png \
  --preview-pdf /app/output/synthetic/synthetic-preview.pdf
```

Inputs:

- `examples/synthetic/input/case.json` and `task.md`;
- `input/semantic_graph.json` (typed semantic graph);
- `input/source/figure03.svg`, `caption.md`, `methods.md` (clearly synthetic fixture sources);
- `input/data/assay.csv` (10 actual parsed CSV rows, synthetic numbers);
- `examples/synthetic/README.md` (relationship/data inventory).

Outputs:

- editable layered `figure.svg`;
- `semantic_graph.json` with resolved paths, hashes, headers, and row mappings;
- `validation_report.json` and `source_comparison.json`;
- top-level-contract `result.json`, including `export_pdf` and every arbitrary contract key;
- `export_report.json` with detected tools, attempts, and structural PNG/PDF checks;
- optional real `synthetic-preview.png` and `synthetic-preview.pdf` under the chosen output directory.

Source-to-final comparison covers semantics and provenance, not pixel equality. The compact final layout intentionally differs from the input figure.

## Validate a new case

An agent must inspect the actual materials and author the source-grounded graph first; `srn.py` deliberately does not infer science. Then run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/srn.py \
  --graph /app/work/semantic_graph.json \
  --output-dir /app/output \
  --preview-png /app/output/figure.png \
  --preview-pdf /app/output/figure.pdf
```

Return codes: 0 = graph built (result can still be honestly `partial` for evidence/export gaps); 1 = semantic errors, SVG withheld; 2 = I/O/parsing failure. See `references/schema.md` and `references/runtime.md`.

`--preview-pdf` preserves the existing CLI and adds an independent optional PDF target. A conventional `export_pdf`/`preview_pdf` contract key also triggers export automatically, as does any non-core string contract value ending in `.pdf` (case-insensitive). Multiple distinct PDF paths are exported separately. Generic suffix detection only selects a requested target: it never treats a pre-existing PDF as a fresh success. A PDF is successful only after `%PDF-`, at least one `/Type /Page`, and terminal `%%EOF` checks; PNG checks signature and terminal IEND. Fresh temporary outputs prevent stale-file success. `export_report.json` records tool detection, all attempts, statuses, and validation. Missing/failed tools leave requested contract values null and make the result partial.

For editing existing SVG, do not use the renderer as a rebuild path. Use `scripts/patch_svg.py` and `references/editing.md` to preserve the original and all unmodified IDs/styles.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_negative.py \
  --example-dir examples/synthetic \
  --report /app/work/negative-test.json

PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_semantics.py \
  --example-dir examples/synthetic \
  --report /app/work/semantic-matrix.json

PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_exports.py \
  --example-dir examples/synthetic \
  --report /app/work/export-test.json
```

The negative harness invokes full invalid builds and requires return code 1 for inhibition retyped as material flow and an unsupported catalysis endpoint. The regression matrix covers cycles/feedback, false feedback, generic activation arrows, disconnection, branch/join declarations, phase cycles, and bad CSV headers. Export regressions cover structural PDF rejection, no-tool behavior, stale-PDF non-claims, conventional/generic PDF keys, arbitrary top-level keys, and honest partial results. Local verification evidence may be kept outside the bundle; no nested `verification/` directory is part of the skill.

## Limits

The program validates an explicitly supplied graph and source transcription; it cannot independently prove an agent visually inspected a paper. Scientific judgement remains source-bound agent/native review. The compact renderer is not a general diagram editor, and its layout does not repair bad semantics. Primary biological figure03/caption/methods missing means `partial`, never domain-knowledge completion. At most two semantic correction/review rounds after initial extraction are recommended within 64 requests/900 seconds.
