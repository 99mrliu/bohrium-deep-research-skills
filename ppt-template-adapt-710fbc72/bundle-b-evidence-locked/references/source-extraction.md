# Source extraction notes

## Extractor precedence

1. `pdftotext -layout` — preserves columns well enough for anchor matching.
2. PyMuPDF (`import fitz`) — fallback when poppler is absent.
3. OCR via the runtime ocr tool — only when the text layer is empty/garbled;
   anchors from OCR text are intrinsically less reliable and must be flagged.

## PDF page vs printed page

Papers with front matter (title page, roman numerals) shift printed numbers.
All anchors, evidence entries and the visible `来源:` line use **PDF page
numbers** (1-based, as split by the extractor). If the task demands printed
numbers, record the offset in the change log and apply it uniformly.

## Getting figures out

- `pdfimages -list` inventories embedded rasters per page; `pdfimages -png
  -f N -l N paper.pdf fig` extracts them at native resolution.
- Vector figures have no embedded raster: render the page region with
  `pdftoppm -png -r 200..300 -f N -l N -x -y -W -H` (crop box in pixels) so
  axes and legends stay crisp; never screenshot at screen resolution.
- Check `images_per_page` in the source index before promising a figure.

## Tables

Dense tables are best rebuilt as native pptx tables (readable, editable);
transcribe cell values from the extracted text and re-run
`check_numbers.py`, which will flag any transcription slip. Very wide tables
may instead be rendered from the PDF page region — say so in the evidence
entry (`kind: "table"`, anchor = the table's caption line).

## Equations

Extracted text usually mangles equations. Cite them as `kind: "equation"`
with the equation number as `ref` and the surrounding sentence as anchor;
render the equation region from the PDF for the slide.
