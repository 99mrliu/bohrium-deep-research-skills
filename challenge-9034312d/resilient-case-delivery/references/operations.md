# Operations, checkpoints, and failure semantics

## Stage ledger

The runner atomically writes `checkpoint.json`, `manifest.json`, and `result.json` in the output directory. It writes an early checkpoint/result before source validation and refreshes the checkpoint/result after each stage.

| Stage | Work | Typical degraded behavior |
|---|---|---|
| `intake` | Read case/task/agent spec; hash actual materials; create manifest and input fingerprint | Missing or malformed required inputs are recorded; downstream science is not guessed |
| `validate` | Validate contract roles, source readability, spec semantics, CSV cells, diagram references, or exact SVG match counts | Main artifact unavailable with precise source error; report still delivered for a valid case |
| `render` | Create source-bound editable SVG/data mapping or apply literal patches to an existing SVG | Skipped if validation fails; modest layout failure never triggers auto-install or answer fabrication |
| `export` | Independently detect installed PNG/PDF exporters; validate PNG signature/IHDR/dimensions/IEND or PDF header/xref/catalog/page/EOF structure | `tool_unavailable` only for affected requested formats; SVG/result survive |
| `report` | Record actual sources, availability, changes, direct CSV comparison, inspection, and limits | Always attempted for a bootstrapped case |
| `project_result` | Atomically project every dynamic contract key and final artifact availability | Result survives independently of scientific/render artifacts |

Stage status is `succeeded`, `partial`, `failed`, or `skipped`; final case status is only `success`, `partial`, or `failed`. Each stage has `error_taxonomy`, structured error objects, and an action description. Checkpoint `pending_stages` makes interrupted progress visible. The runner adds no timestamps or random run IDs, so its deterministic artifacts are reproducible for identical inputs and environment. External exporters may embed tool-specific metadata; actual output hashes are reported without claiming byte identity across tools or fresh exports.

## Error taxonomy

| Kind | Use when | Required honest response |
|---|---|---|
| `missing_material` | File, usable rows, specification, or required figure observations are absent | Null affected contract value; explain what was not created |
| `unreadable` | Permission, I/O, encoding, CSV/PDF-extracted text read failure | Do not quote or plot bytes that could not be read |
| `ambiguous` | Duplicate IDs/headers, unexpected replacement counts, duplicate output paths, unresolved alternatives | Do not silently choose a match |
| `tool_unavailable` | A requested PNG/PDF exporter is absent, all detected exporters fail, or output structure is invalid | Keep SVG/result/report and other valid formats; no install, fake preview, or fake success |
| `semantic_defect` | Malformed JSON/spec, unsafe contract, unknown columns/mode, invalid numeric cells, invalid SVG target | Nonzero exit and honest result; fix spec/source, not the error label |

An artifact is `available` only if its actual file can be read and hashed. Otherwise it is `unavailable` for a requested output or `not_requested` for an optional output. PNG and PDF requests and errors are tracked independently. Contract projection is an actual path string only for an available artifact and `null` otherwise, including PDF contract keys. Availability never means scientific correctness. `checkpoint.json` `export_details` and the Markdown report retain per-format request state, artifact key, exporter attempts, validation, selected exporter, and reuse state.

## Exit and final-status behavior

- Exit **0 / success**: all requested artifacts are readable and no stage error remains.
- Exit **2 / partial**: a valid case has useful delivery but an error or requested unavailable artifact remains. Missing required CSV and missing requested preview exporter both use this path.
- Exit **3 / failed**: malformed/unreadable case bootstrap or an invalid case contract prevents establishing the normal delivery. The runner still attempts `result.json`, `manifest.json`, and `checkpoint.json`.

Invalid case handling is intentionally nonzero: automation cannot mistake a partial/failed result for a clean scientific delivery. The JSON remains available for orchestration and diagnostics.

## Atomicity and manifest

JSON and SVG/report/data writes use a temporary file in the destination directory, flush/fsync, then `os.replace`; `result.json` is replaced after every stage and at final projection. No consumer should see a half-written JSON document. The manifest contains actual resolved input paths, roles, kinds, source-provided versions, byte counts, SHA-256, availability, and read errors. It is a manifest of files actually read, not a list of expected answers.

## Resume and bounded improvement

`--resume` compares a fingerprint over the runner version, actual input paths/hashes/errors, independent PNG/PDF preview requests, and explicit exporter override. Intake and validation always rerun. Only successful intact render/export stages with a matching fingerprint are reused; PNG and PDF files are structurally revalidated before reuse, and the report/result are rebuilt. Changed/missing/restored sources or either preview flag change the fingerprint and stale contract artifacts are removed before rebuilding. A failed preview can be retried after tool availability changes without discarding the source SVG when the fingerprint otherwise matches.

Independent input cases must use separate output and work directories. Do not combine several cases into one manifest or use a checkpoint across cases. Resume from `/app/output/checkpoint.json` for that same case only.

Platform work is bounded by 64 model requests and 900 seconds, with at most two agent review rounds. Save the honest partial early; inspect actual artifacts and spend remaining effort on source correctness or spec repair. The runner performs one pass and no autonomous correction loop. Optional export never gates SVG delivery.

## Preview tool support and structure

PNG auto-detection supports `rsvg-convert`, Inkscape, ImageMagick, `sips`, and CairoSVG. PDF auto-detection supports `rsvg-convert`, Inkscape, Chrome/Chromium (including standard macOS application paths), and CairoSVG. Use `--preview-pdf` independently of `--preview-png`, or declare the PDF contract entry as required. No tool is installed and no PDF is attempted for an optional unrequested contract entry. CairoSVG may be an installed command or an importable module; the export must still exit successfully and validate before it is considered usable.

Exports go to a temporary file in the destination directory and are atomically moved into place only after validation. PNG checks signature, initial IHDR, nonzero dimensions, and final IEND. PDF checks `%PDF` at byte zero, final `startxref`/`%%EOF`, an in-range xref table or xref-stream object target, `/Root`, and `/Type /Page`. Failed/invalid files are removed rather than projected as available. The structural check does not replace visual inspection or scientific review.

## Explicit no-install negative control

For deterministic testing only:

```bash
RESILIENT_CASE_PREVIEW_EXPORTER=none python3 scripts/run_example.py \
  --example-dir examples/synthetic --output-dir /tmp/case-negative --preview-png
```

This must exit 2, retain an available SVG and data mapping, set `preview@PNG` to null, classify the export error as `tool_unavailable`, and keep valid `result.json`. The same override with `--preview-pdf` tests PDF absence; if both formats are requested, each has its own unavailable artifact record. Unset the override for normal auto-detection. A selected executable can also be named explicitly, including `cairosvg`; this is a deterministic control, not an installer. No dependency installer exists in this Skill.
