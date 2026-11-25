# Source intake, preservation, data encoding, and export

Every included example is **SYNTHETIC — NOT A SCIENTIFIC CLAIM**.

## Formal intake

Read `/input/case.json`, `/input/task.md`, and `/input/figure-workorder.json`; use `/app/work` for intermediates and `/app/output` for finals. PDFs below the input root are read with PyMuPDF and page text is copied into `work/source_text/`. This is not scientific relation extraction. `figure03*` original/caption files, `data/` files, and other supporting sources are checksummed and listed in `result.sources`. `case.source_files` can assert exact required relative paths and fails on omissions.

A curator must read the actual paper PDF, original Figure 3, caption and body text, data, and figure work order, then encode the process assertions in `case.model`. Data values are not silently converted into activation or inhibition. Association is not promotion to activation. A visually nearby molecule is not automatically an input, output, or modulator.

The runner initially writes a partial result. Any semantic issue blocks rendering and leaves the model, audit, and content map for repair. This avoids turning a failed parse into a plausible final mechanism.

## Source-preserving SVG editing

The preferred original is `input/figure03.svg`. It is copied byte-for-byte to `work/original/figure03.original.svg`. The XML root and existing children are retained and the `process-semantics-generated` layer is appended. Canvas dimensions may expand to accommodate generated semantics. The delivered `editable_source.svg` remains XML, with separately addressable entity, process, and arc IDs.

PDF/raster originals are inventoried but do not support this source-preserving SVG path. Without `figure03.svg`, the runner generates a new SVG and adds an explicit uncertainty; it must not claim that source graphics were edited. Original raster content is never substituted for an editable semantic model.

## Export and inspection

After semantic validation, Python standard-library XML/string code creates the final SVG. PyMuPDF opens that actual file and writes `export.png` at 2× and `export.pdf` through SVG-to-PDF conversion. Both derive from the same delivered SVG. Export exceptions leave partial status and a nonzero exit.

Inspect the SVG and both exports for text, arrow direction, T-bars, clipping, and source-layer fidelity. PyMuPDF SVG support and local font substitution can alter visual details. Automatic layout is deterministic and designed for small figures; it is not full SBGN layout, automatic scientific extraction, or publication-quality typography for arbitrary dense networks.

`result.json` emits every declared output-contract field; unknown custom fields are null until a corresponding implementation is added. Source paths are input-relative and final artifact links are output-relative. `change_records` reflects operations actually performed, never an anticipated success.
