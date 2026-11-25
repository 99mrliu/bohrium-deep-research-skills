# Runtime and output contract

Defaults are exactly `/input`, `/app/work`, `/app/output`. The runner reads real `case.json`, `task.md`, workorder, data spec, and raw data each time. `--input/--work/--output` support isolated validation but never trigger example fallback. Case/spec/workorder/raw/source SHA-256 values are recorded.

## Output contract

`output_contract.required_files` is an array of required relative filenames. `output_contract.artifacts` optionally remaps these logical keys:

| Logical keys | Default file | Meaning |
|---|---|---|
| `derived`, `derived_csv` | `derived.csv` | Observation-level tidy data with row checksums, statistics and encodings |
| `group_summary`, `group_summary_csv` | `group_summary.csv` | Independent-sample group summaries |
| `audit`, `data_audit` | `data_audit.json` | Statistics, filter/transform config, row provenance, channels and marks |
| `svg`, `chart_svg` | `chart.svg` | Real-text editable chart or preserved edited source |
| `png`, `chart_png` | `chart.png` | Actual 2× raster rendering |
| `pdf`, `chart_pdf` | `chart.pdf` | Actual vector PDF |
| `sources` | `sources.json` | Actual input hashes/roles |
| `uncertainty` | `uncertainty.json` | Errors and source/data limitations |
| `change_records` | `change_records.json` | Declared scopes and actual source edits |
| `result` | `result.json` | Dynamic completion record |

Unmapped logical outputs keep defaults. Absolute paths and `..` are rejected. Arbitrary additional output-contract fields (for example reviewer/case metadata) are preserved both at result top level and in `output_contract`; they are not mistaken for files.

Result includes actual `case_id`, `status`, `partial`, `generated_files`, `artifact_checks`, `sources`, `uncertainties`, `change_records`, and `errors`. Result itself is not self-hashed. SVG must parse and contain real non-empty text; PNG/PDF signatures and CSV headers are checked; hashes and byte counts describe actual files.

## Failure semantics

Success prints a JSON summary and returns 0 only after required artifacts and format checks pass. Data/spec/column/numeric/scale/edit/render errors print to stderr and return 2. If even partial result writing fails, return 1. The runner attempts sources/uncertainty/change records and result on failure, using resolved case ID or `UNRESOLVED_CASE_ID` if the case itself is unreadable. Partial output has no success claim.

Re-running an output directory may overwrite same-named artifacts. Validate in a fresh directory if comparing cases. The implementation does not delete unrelated files or perform network/Git operations.

## Honest limitations

- Row checksums prove which raw object was read, not biological authenticity or external source correctness.
- Source-provided p/log2FC are transformed, not independently recalculated without the relevant test/design data.
- Independent sample definition is the configured sample ID; experimental-unit mistakes in upstream metadata cannot be detected automatically.
- A preserved source SVG is not guaranteed to visualize the newly derived values; the runner warns and provides candidate scales separately. Create mode is required for synchronized rendering.
- Numeric domain/format checks and visual inspection cannot prove a chosen statistical model is scientifically appropriate.
