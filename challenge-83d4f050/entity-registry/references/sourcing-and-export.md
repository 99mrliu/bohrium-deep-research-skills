# Sourcing, work orders, source-preserving editing, and export

Every included example is **SYNTHETIC — NOT A SCIENTIFIC CLAIM**.

## Production intake

The formal root is `/input`; execution uses `/app/work`; only final artifacts belong in `/app/output`. `case.json`, `task.md`, and `figure-workorder.json` are required. The work order is retained for traceability. The runner does not invent missing editorial instructions.

Paper PDFs anywhere below the input root are opened with PyMuPDF and page text is copied to `work/source_text/`. This is plain-text extraction for curator review: the script does not turn prose into entities, aliases, or relations. `figure03.caption.txt` (or another `figure03*.txt/md`) is retained verbatim in work. Data under `data/` and all other source files are checksummed and classified in `result.sources`. `case.source_files` can require exact relative paths; missing entries fail the run.

The normalized registry is accepted only from `case.registry`. A human curator must reconcile paper text, original Figure 3, captions, and real data before encoding it. This prevents fluent but unsupported scientific extraction.

## SVG editing

`figure03.svg` is the preferred original. It is copied byte-for-byte to `work/original/figure03.original.svg` before parsing. The renderer parses XML, preserves the original root's existing children, expands the canvas when needed, and appends one identifiable `entity-registry-generated` layer. Existing source elements are not rasterized or discarded. The result remains editable XML in `editable_source.svg`.

An original PDF, PNG, or JPEG is inventoried but not treated as editable SVG. If no `figure03.svg` exists, the runner generates a new SVG and explicitly records this limitation in `uncertainty`. Do not describe that path as source-preserving editing.

## Exports and status

PyMuPDF reads the final SVG, writes a 2× PNG, converts the SVG document to PDF bytes, and writes `export.pdf`. Export occurs only after identity validation and mention resolution pass. Export failure leaves the earlier result/audit/map available and marks the run partial with a nonzero exit.

All timestamps and change records describe actual operations. `content_map` and `editable_source` values are relative artifact paths, while `sources` records input-relative paths and SHA-256 hashes. Unknown output-contract fields are emitted as null rather than silently discarded; add an explicit implementation before treating a custom field as fulfilled.

## Review boundaries

Validation cannot resolve an intentionally ambiguous label without context, verify a source locator's external accuracy, or decide biological synonymy. Curate those decisions upstream and retain the reasoning in the source record. Automatic layout is deterministic, not a substitute for visual review of dense figures. PDF font substitution and PyMuPDF's SVG feature coverage can affect appearance; inspect both exported artifacts before publication.
