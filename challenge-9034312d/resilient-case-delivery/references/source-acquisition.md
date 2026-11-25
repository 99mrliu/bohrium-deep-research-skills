# Source acquisition and inspection

All commands below operate on actual inputs and write extraction work to `/app/work`. Check tool availability first. Do not auto-install anything and do not mistake an unavailable parser for an empty paper.

## PDF and text command guidance

Discover the actual case-provided filenames from `case.json` and the input directory; the following variables are examples, not assumed filenames:

```bash
PDF=/input/actual-paper.pdf
command -v pdftotext
command -v pdftoppm
mkdir -p /app/work/extracted
pdftotext -layout "$PDF" /app/work/extracted/paper.txt
pdftoppm -f 3 -l 3 -singlefile -png -r 180 "$PDF" /app/work/extracted/page-03
```

Use the actual page containing `figure03`, which may not be PDF page 3. `pdftotext -layout` can preserve captions and column order better than raw text but does not establish biological relationships. If the PDF has a text layer, read surrounding methods/caption text as well as inspecting the figure. If `pdftotext` or `pdftoppm` is absent, record `tool_unavailable` and retain any actually supplied PDF/PNG sources; do not claim to have inspected a rendered page.

For plain text, read the actual UTF-8 file directly. When an encoding is genuinely undecodable, mark it `unreadable`; do not silently replace arbitrary bytes and then quote the result. Small extraction helpers may use Python stdlib `pathlib` and `csv`. Reference the extracted file as a `/app/work/...` material only when it was actually generated, and retain the original PDF as the primary source with page/figure locators.

Optional PNG preview exporters are detected independently by the runner (`rsvg-convert`, Inkscape, ImageMagick, `sips`, or CairoSVG). Requested PDF previews use installed `rsvg-convert`, Inkscape, Chrome/Chromium, or CairoSVG. Their absence only degrades the affected requested preview; it must not block editable SVG/result delivery. PDF is not exported unless declared as required or requested with `--preview-pdf`. QuickLook thumbnails are deliberately not accepted as scientific previews because they may crop the canvas. Export structure is validated separately from source/scientific inspection.

## Biological `figure03` inspection protocol

Inspect the supplied figure image or actual rendered PDF region at legible magnification. Use the original labels and visible marks. In the agent-created specification, record:

1. Source path, hash (filled by the runner), source-provided version, PDF page, panel/region, and `figure_id: figure03`.
2. Every observed biological entity needed by the task, distinguishing visible labels from nearby caption/method context.
3. Compartments or containment only where represented; note crossing lines that are not evidenced interactions.
4. Directed arrows and their actual endpoints, including inhibition or other line styles if visible. Do not reverse a direction to fit a common pathway.
5. Numbered sequence, branches, feedback, or boundaries only when seen or directly supported by task text.
6. Ambiguous characters, occluded arrows, tiny labels, and conflicting caption/figure readings as uncertainties. Resolve with another look at the source, not memory.

A figure inspection is evidence for the specification, not permission to add a familiar mechanism. The runner's `diagram` mode preserves the declared entities and edges, but its export success does not validate biological correctness. Compare the final SVG labels/directions against these observations in each of at most two bounded agent review rounds.

## Charts from actual source data

Before writing the chart specification:

- Open the actual CSV and record its header exactly, including capitalization and units in separate columns if present.
- Count data rows and inspect all rows used; do not infer data from a plot thumbnail when source CSV was requested.
- Identify the true primary source and its version/locator. If a CSV conflicts with a paper figure, report the conflict rather than silently selecting whichever looks smoother.
- Check duplicate headers, missing cells, numeric parsing, series names, row order, and units. Multiple plausible mappings are `ambiguous` and need source/task clarification.
- Plot actual x/y cells only. No interpolation, fitted substitute, arbitrary control, normalized value, or synthetic replacement may be presented as source data.

The runner records raw source strings, parsed values, CSV row locators, and a direct cell-to-coordinate comparison. Inspect `data_mapping.json` and the report's primary-source table after running. The comparison establishes faithful transfer from the declared CSV, not agreement with every external primary source; any separate source comparison found by the agent must be included explicitly in the specification/report uncertainty or observation record.
