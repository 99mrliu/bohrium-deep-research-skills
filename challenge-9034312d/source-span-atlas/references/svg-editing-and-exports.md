# Source-preserving SVG edits, exports, fonts, and reuse

## Edit means targeted edit, never rebuild-and-relabel

For an edit task, retain the original SVG unchanged under `/app/work`. Reconstruct/extend the atlas for its scientific groups, validate new semantics against actual sources, and pass the gate before patching. Only then copy to a new `/app/output` SVG using XML-located byte-range edits. Do not run the simple renderer over the original and call that an edit.

The helper supports existing single-run text and existing attributes:

```bash
python3 /skills/weekly-skill/scripts/patch_svg.py \
  --input-svg /app/work/original.svg \
  --patch /app/work/patch.json \
  --gate-report /app/work/atlas.json \
  --output-svg /app/output/edited.svg \
  --records /app/output/svg_changes.json
```

Example patch:

```json
{
  "patches": [
    {
      "element_id": "existing-label",
      "assertion_id": "A_LABEL",
      "new_text": "Source-supported label",
      "attributes": {"font-size": "14"},
      "reason": "Correct actual source term and improve legibility"
    },
    {
      "element_id": "existing-arrow",
      "assertion_id": "A_DIRECTION",
      "attributes": {"x2": "412.5"},
      "reason": "Reconnect the already evidenced arrow endpoint"
    }
  ]
}
```

The helper parses XML with stdlib Expat to locate byte offsets, replaces only the target start-tag/text spans, leaves all other bytes unchanged, reparses the result, refuses duplicate/missing targets and input/output aliasing, verifies unchanged bytes outside ranges, and emits before/after hashes and records. It does not serialize an ElementTree back over the source.

Limitations are intentional: no insertion/deletion, no nested `<tspan>` whole-parent replacement (target each child), no adding absent attributes, no arbitrary geometry redesign. If the requested edit needs unsupported operations, implement an equally targeted XML fragment edit only if it can preserve/audit all unaffected bytes; otherwise return `partial` with the exact limitation. Never claim a rebuild is source-preserving.

After patch:

1. Run `source_span_atlas.py` with `--audit-svg /app/output/edited.svg`, not in rebuild mode. This audits unique IDs and source-to-visual coverage without replacing the edited SVG.
2. Put actual patch before/after records in the atlas `change_records` before the final audit, or merge them into the final `result.json` without dropping contract keys.
3. Ensure `change_records` states actions, element/assertion IDs, exact before/after text/attributes, reasons, gate verdict, and source hashes. Explicitly record important unchanged elements when the native agent reports them.
4. Re-export and visually compare before/after. Confirm that only intended scientific meaning changed.

## Editable SVG output

The generation renderer creates named Inkscape-compatible layer groups (`Background`, `Titles`, `Evidence-backed relations`, `Entities and ordered steps`, `Evidence-backed notes`, `CSV-linked charts`, `Evidence legend`). Scientific groups retain stable IDs, assertion IDs, evidence statuses, source IDs, `<title>`, and evidence `<desc>`. Text stays as `<text>/<tspan>`, not paths. The core writes UTF-8 SVG and does not need a GUI.

The renderer is intentionally secondary and simple: horizontal entity rows, ordered step rows, notes, and one or more basic CSV charts. It has no autorouter, dense graph optimizer, publication template engine, or automatic conflict resolver. For complex layouts use native SVG targeted edits while preserving the atlas/coverage contract.

## PNG/PDF export

Core dependencies are Python 3 stdlib. PNG and PDF exports are optional independent flags, `--preview-png` and `--preview-pdf`; each can be requested alone or both can be requested together. They honestly probe, in order:

1. importable CairoSVG and its native Cairo library, falling through if import or conversion fails;
2. `rsvg-convert` on PATH;
3. Inkscape on PATH;
4. an existing headless Chrome/Chromium browser. PNG uses the executable in `SOURCE_SPAN_ATLAS_BROWSER`; PDF first honors that variable, then autodetects Chrome/Chromium on PATH and in standard installed application locations. No executable path is stored in the Skill.

No install is attempted. Browser PNG export uses the actual SVG width/height, pixel scale 1, and a timeout. A tool's return code alone is insufficient: output existence, PNG signature, and pixel dimensions are checked for PNG. PDF output is checked in the actual bytes for `%PDF-` header, terminal `%%EOF`, a real page object, a positive `/Pages` `/Count` consistent with page objects, positive `/MediaBox` dimensions, and a valid `startxref` target. Invalid/stale PDF bytes are removed rather than claimed. Attempts/errors, including per-tool PDF structural results, go to `export_report.json` (PNG) and `pdf_export_report.json` (PDF); command arguments and page dimensions/count/hash are recorded for PDF. Structural checks do not replace visual or scientific inspection. Any missing/failed requested export yields honest `partial` with editable SVG retained and no artifact path for that failed format.

## Fonts and preflight

The SVG family stack is `Arial, Helvetica, Noto Sans CJK SC, Microsoft YaHei, sans-serif`. Availability varies. SVG text is editable but fonts are **not embedded** by the core; never claim embedded fonts merely because an SVG opens. Inspect PNG/PDF for missing glyphs, substitution, CJK tofu, line wrapping, clipping, and baseline/arrow overlap. If a required font is missing, retain SVG, document it, and use only an actually installed licensed font. Do not silently convert every label to paths, because that destroys text editability.

Exports are RGB. No CMYK conversion, embedded ICC profile, font licensing guarantee, journal-specific dimensions, or PDF preflight is claimed. Record target format, actual pixel/page dimensions, requested DPI if applicable, tool/version where available, and actual visual checks. A screenshot is not a substitute for the editable SVG.

## Reusable resources

- `atlas_lib.py`: normalization mapping, source-span validation, locators, semantic/figure review validation, CSV mappings, simple layered SVG, bidirectional coverage.
- `source_span_atlas.py`: CLI, deterministic atlas/report/result, optional honest export.
- `patch_svg.py`: non-rebuilding targeted edit helper and before/after provenance.
- `extract_pdf_text.py`: actual PDF text extraction with hashes/page separators when `pdftotext` exists.
- `examples/minimal`: fully labelled synthetic source/input/original figure/CSV/expected outputs.
- `tests/negative`: unsupported-connection fixture plus runnable test wrapper.
