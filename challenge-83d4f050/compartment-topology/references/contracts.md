# Runtime, output, and failure contracts

## Inputs and directories

Defaults are exactly `/input`, `/app/work`, and `/app/output`. `case.json` and `task.md` are read for every run, and their SHA-256 values are recorded along with topology/workorder/source hashes. `--input`, `--work`, and `--output` exist for isolated validation; they do not enable examples as implicit fallback. Output filenames cannot be absolute or contain `..`.

The runner creates its work/output directories. Temporary PDF-derived SVG is placed only in the selected work directory. Final output contains only files named by the output contract/defaults.

## Outputs

| Logical name | Default | Content |
|---|---|---|
| `layout` | `layout.json` | Canvas, compartment bounds, node centers/sizes/layers, routes, main path, branches, feedback reasons |
| `svg` | `figure.svg` | Editable source or generated SVG with true text and stable IDs |
| `png` | `figure.png` | Actual raster rendering at 2× scale |
| `pdf` | `figure.pdf` | Actual single-page vector PDF |
| `audit` | `topology_audit.json` | Passed/violations and explicit topology/layout checks; source-preservation audit when relevant |
| `sources` | `sources.json` | Actual input paths, roles, byte counts, SHA-256 and synthetic flag |
| `uncertainty` | `uncertainty.json` | Warnings/errors, including source geometry limitations |
| `change_records` | `change_records.json` | Workorder changed/unchanged declarations and per-operation before/after records |
| `result` | `result.json` | Dynamic case/status/artifacts/errors plus every contract field |

If `artifacts` is absent, all defaults are produced. Example custom mapping:

```json
{
  "required_files": ["custom-layout.json", "figure03.svg", "figure03.png", "figure03.pdf", "result.json"],
  "artifacts": {
    "layout": "custom-layout.json",
    "svg": "figure03.svg",
    "png": "figure03.png",
    "pdf": "figure03.pdf",
    "result": "result.json"
  },
  "reviewer": "case-specific value retained in result"
}
```

Unmapped provenance/audit files retain their default names. Additional arbitrary `output_contract` fields are retained both at result top level and under `output_contract`; the runner does not pretend they are artifacts.

## Completion and partial failure

Before success, required rendered files must exist and the final artifacts must be non-empty. SVG must parse and contain non-empty text, PNG must have its real signature, and PDF must have its real header. `artifact_checks` records actual bytes and hashes. Result JSON is not self-hashed, avoiding a recursive checksum.

Validation/constraint/operation errors and rendering exceptions are printed to stderr and return 2. Failure to write even the partial records returns 1. On failure the runner attempts sources, uncertainty, change records and `result.json` with the resolved `case_id` (or `UNRESOLVED_CASE_ID` if case JSON itself was unreadable), `status: "partial"`, `partial: true`, and errors. It never converts a failure to success because some artifacts exist.

The command prints one JSON summary only after success. Visual inspection remains necessary: file signatures and topological audits do not prove aesthetic clarity, biological correctness, or semantic equivalence of a third-party source drawing.
