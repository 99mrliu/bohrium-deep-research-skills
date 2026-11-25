# Runtime delivery and honest partial checkpoints

## Paths and inputs

Official input is `/input/case.json`, with task text at `/input/task.md` (or platform-provided `/task.md`). Read actual referenced files; original source PDFs may not have a pre-extracted semantic layer. Use `/app/work` for graph drafts, source renders, mutants, edit instructions, and other intermediates. Put final actual artifacts and all final reports in `/app/output`.

## Early checkpoint

After source inventory, write an initial result with original `case_id`, original contract keys (null if not yet produced), `status: partial`, current `sources`, explicit `uncertainties`, empty/current `change_records`, and `paths`. Also checkpoint the source-review notes and typed graph under `/app/work`. This protects a valid partial result if budget or export fails. Do not mark an uninspected primary figure as reviewed.

## Completion and evidence

Final `/app/output/result.json` must have every original output-contract key at top level plus `case_id`, `status`, `sources`, `uncertainties`, `change_records`, and `paths`. Ensure these are actual final paths, not intended paths; paths inside the output directory are reported relative to it for portability, while external explicit CLI paths may be absolute. SVG should remain layered/editable, with source-preserving patch audits for edits. Export checks state exporter and availability truthfully. Use real rendered PDF/PNG previews when requested/available and inspect them.

Write `/app/output/export_report.json` (or the contract's `export_report` path) on every build. It records installed-tool detection, export attempts, requested outputs, and structural checks. `--preview-pdf` adds an explicit target; conventional `export_pdf`/`preview_pdf` and generic string contract values ending in `.pdf` automatically request real PDF export. PDF success requires a `%PDF-` signature, at least one page object, and terminal `%%EOF`; PNG success requires signature and IEND. Conversion uses a fresh temporary file and only validated output is copied to its final path. Missing tools, failed conversion, or malformed output leaves the affected contract key null and produces `partial`, never a suffix-only placeholder or stale-file success. Existing arbitrary non-PDF contract files are still linked top-level when present and null otherwise.

- `success`: actual required sources inspected, no semantic errors, source semantic comparison matches, required real charts bound, and all required exports produced.
- `partial`: usable graph/artifacts but missing primary figure03/caption/methods, unverified source comparison, unavailable requested export, or another explicit contract gap.
- `failed`: unresolved semantic validation errors or inability to provide the central artifact. Include reports and uncertainty rather than forcing output.

Material missing, scientific ambiguity, and software/export failure are distinct uncertainties. Never convert one into inferred facts. Runtime artifacts may be PDF/PNG; the distributed skill otherwise uses text resources, with only explicitly permitted verification PNG/PDF previews kept outside the bundle.

## Budget discipline

64 requests/900 seconds are hard outer limits. Extraction and source topology take priority over layout. At most two semantic review rounds after initial graphing. Deterministic scripts use no network, wall-clock timestamps, random numbers, or external packages. Re-running unchanged inputs produces byte-identical graph/SVG/validation content. Third-party browser/PDF exporters may embed run-specific metadata, so PDF bytes and their recorded SHA-256 can legitimately differ between successful runs.
