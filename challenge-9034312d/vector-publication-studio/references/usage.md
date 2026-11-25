# Vector Publication Studio

A text-only, deterministic scientific SVG publication Skill. The main artifact is live, layered SVG plus a source specification; export and source-preserving edit reports make the result independently checkable.

## Contents

- `SKILL.md`: trigger, mandatory runtime contract, source-first procedure, visual review and failure behavior.
- `scripts/studio.py`: stdlib SVG builder, automatic rank/lane layout, obstacle-aware orthogonal routing, glyphs, marker semantics, real CSV charts, optional CairoSVG export and structural QC.
- `scripts/patch_svg.py`: Expat byte-span edits that do not reserialize an existing SVG.
- `scripts/run_case.py`: actual `/input` → `/app/output` runner and top-level output-contract mapping.
- `scripts/run_example.py`: explicit synthetic example + independent source-preserving edit demonstration.
- `references/`: source-spec schema, scientific evidence rules, and publication/export/QC guide.
- `examples/synthetic/`: clearly synthetic input, CSV, source spec, and text SVG figure.

## Quick start

From this bundle directory:

```bash
python3 scripts/run_example.py \
  --example-dir examples/synthetic \
  --output-dir /tmp/vps-example \
  --preview-png /tmp/vps-example/preview.png --pdf
```

Export tries CairoSVG, `rsvg-convert`, Inkscape, then Chrome Headless; nothing is installed. Tool availability and native-library failures are recorded. If none succeeds, run `studio.py build` and disclose that preview/PDF could not be produced.

All bundled example labels, topology and numbers are synthetic. No font is embedded. SVG source remains text-editable. Generated runtime PNG/PDF files belong outside this bundle.

Version: 1.0.0. License/compatibility note: no external template or glyph artwork is redistributed; glyphs are constructed from native SVG primitives.
