# Template, rendering, and result behavior

## Input discovery and templates

`prepare` recursively inventories actual files and also resolves explicit path strings under case keys related to materials, artifacts, work orders, templates, sources, documents, and inputs. PDFs are verified by signature and successful PyMuPDF opening. PPTX files must be valid packages with `ppt/presentation.xml`, at least one master, and one layout. A valid template inventory records dimensions, existing slide count, masters, layouts, placeholder types/indices, and theme colors where readable.

A single valid template is selected automatically. Multiple valid templates require explicit `template_path` in the plan. Do not select by a preferred filename.

## Native generation

The builder removes existing slides only in generation mode. Adapt mode requires every original ID to be edited/preserved or explicitly removed; existing layouts and unspecified visual content stay native. Layout selection for appended slides prefers `Title Slide`, `Section Header`, or `Title and Content` by kind across all masters, then falls back to actual title/body placeholder capabilities. An optional exact `layout_name` or zero-based `layout_index` overrides selection only for appended slides and is validated.

Title placeholders are identified by native title/center-title type. Body candidates are native body/object/subtitle/vertical variants sorted by placeholder index. The build report records layout and placeholder indices. A text-box fallback is used only if a selected native layout lacks a body placeholder; a missing title is an error.

Fonts explicitly set by the builder are at least 14 pt; title typography remains inherited from the selected layout/master. Bounded text budgets and aspect-fit images reduce overflow risk, but renderer/font differences mean they do not replace visual inspection. Source captions are added verbatim at 14 pt. Every slide receives notes containing its source-linked evidence IDs, raw quotes, qualifiers, source IDs, pages, and span references; preserved originals retain their previous notes before the appended evidence. Figure/text columns derive from actual body-placeholder geometry and slide dimensions, not hard-coded widescreen positions.

## Asset coordinates and placement

Candidate and explicit bboxes use PDF points, `[x0,y0,x1,y1]`, top-left origin. Candidate extraction combines the actual caption block with neighboring images, vector drawings, and text bounds. Text-only table fallback unions nearby blocks above the caption. The proposal remains visibly reviewable through `page_preview` and `requires_visual_check`.

At build time the selected source page is clipped and rasterized at bounded zoom. The picture is scaled uniformly to fit its slot and centered; width and height are never independently stretched. Original captions are not replaced by custom result labels. Inspect axes, legends, columns, annotations, and surrounding qualifiers. Correct the plan's explicit bbox and rerun if necessary.

## Renderer behavior

The exporter tries `SOFFICE`, `soffice`/`libreoffice` on PATH, then standard macOS/Linux locations. It invokes LibreOffice headlessly with an isolated profile to create a real PDF, and PyMuPDF rasterizes each PDF page to PNG. `render_report.json` records the executable, command/return diagnostics, rendered text, page count, expected-text discrepancies, preview paths, and pixel dimensions.

A usable PPTX without a renderer produces partial status and no fabricated PDF/PNG artifacts. Export errors and preview errors are retained. Success requires the expected PDF page count and one PNG per page. The agent must still inspect every page; file existence alone is not visual verification.

## Result and failures

Prepare always attempts a partial result. Validation reports and the evidence map are written before a validation failure result. Build/validation errors never silently strip factual plan content. Unknown output-contract fields remain null because their semantics cannot safely be invented. Recognizable artifacts/map/compliance/exceptions fields point to real generated content only.

Potential legitimate limitations include missing OCR, ambiguous template choice, unavailable fonts, renderer substitution, imperfect candidate crops, and source extraction order. Put unresolved issues in `uncertainty` and/or structured `exceptions`; downgrade status when they prevent a complete verified deliverable.
