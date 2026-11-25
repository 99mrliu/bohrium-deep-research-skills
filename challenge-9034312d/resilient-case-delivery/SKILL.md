---
name: resilient-case-delivery
description: >-
  Run source-bound scientific figure cases through a deterministic, disk-checkpointed delivery contract. Use when a case requires editable SVG/diagram/chart delivery, optional real PNG/PDF previews, dynamic output_contract projection, actual-input provenance, resume, source-preserving SVG edits, or honest partial delivery when materials or preview tools are unavailable. Includes PDF/text and figure03 inspection guidance; uses only Python stdlib for rendering and never installs tools automatically.
---

# Resilient case delivery

This Skill is a **case runner and contract orchestrator**, not a diagram-only pipeline. It preserves an early recoverable result, checkpoints each stage, hashes the files actually read, distinguishes failure causes, and delivers the scientific SVG independently of optional preview export.

## Runtime entrypoint

At official execution time, read the real `/input/case.json` and `/input/task.md` (or `/task.md`), plus the actual files named by those inputs. Work only in `/app/work`; put final artifacts, `result.json`, `manifest.json`, `checkpoint.json`, and every report in `/app/output`.

1. Inspect the actual task and sources before specifying scientific content. Do not assume facts from a filename or domain label. Do not embed or reconstruct prepared official answers.
2. Follow [references/source-acquisition.md](references/source-acquisition.md) for PDF/text extraction, biological `figure03` inspection, and actual CSV inspection. Use only tools already present; absence is `tool_unavailable`, never a reason to install packages or invent extracted content.
3. Create `/app/work/case_spec.json` from those observations using [references/case-spec.md](references/case-spec.md). The agent—not a prepared answer layer—supplies source identifiers, exact CSV column mappings, inspected entities/relationships, or targeted SVG replacements.
4. Start the runner early enough to create `checkpoint.json`, `manifest.json`, and an honest partial `result.json` before doing any optional improvement:

```bash
python3 /skills/weekly-skill/scripts/case_runner.py \
  --case /input/case.json \
  --spec /app/work/case_spec.json \
  --work-dir /app/work \
  --output-dir /app/output \
  --preview-png
```

Omit `--preview-png` if no preview was requested and no required PNG is in the contract. Add `--preview-pdf` only when a PDF preview is wanted; a `kind: pdf` contract entry with `required: true` also requests it without the flag. The two flags are independent, and PDF is never generated merely because an exporter exists. If the contract has no PDF key, `--preview-pdf` uses the auxiliary `preview.pdf` artifact; a declared PDF key is always preferred. Without `--task`, the runner checks the case-adjacent `task.md`, `/input/task.md`, then `/task.md`; an explicit `--task /task.md` is also accepted. Relative material paths in the specification resolve against the specification directory; official cases should normally use absolute `/input/...` or extracted `/app/work/...` paths.

5. Read back `result.json`, the SVG, the report, and the preview when available. Correct only source/specification defects and rerun. Use no more than **two bounded review rounds** within the platform limits of **64 model requests and 900 seconds**. Do not spend the budget replacing the modest fallback renderer with a rendering project.

## Delivery contract

`output_contract` is dynamic. For an object entry such as:

```json
"any unusual key → [editable]": {"path": "figure.svg", "kind": "svg", "required": true}
```

the runner creates top-level `result.json["any unusual key → [editable]"]` with value `"figure.svg"` when available and `null` otherwise. A string contract value is shorthand for `{"path": value}`; kind is inferred from `.svg`, `.png`, `.pdf`, `.json`, or `.md`. Every original key—including unusual PDF keys—is projected, not just hardcoded `svg`/`png` names. Explicit kinds are `svg`, `png`, `pdf`, `json`, `report`, and `file`. PNG and PDF default to optional (`required: false`) when the field is omitted; set `required: true` when the official task requires one. Reserved result-metadata names, absolute paths, `..`, duplicate paths, and a contract targeting `result.json` are semantic defects.

Every result includes `case_id`, final `status`, `sources`, `uncertainties`, `change_records`, per-artifact `artifacts`, stage/error records, and all original contract keys. Artifact records expose `requested`, `available`, `availability`, actual relative path, bytes, SHA-256, and structured error. Final status is only:

- `success`: every requested artifact exists, is readable, and no stage error remains;
- `partial`: a valid case delivered something useful but material, semantic, or tool limits remain;
- `failed`: case bootstrap itself could not establish an honest case result.

See [references/operations.md](references/operations.md) for exit codes, stage semantics, taxonomy, resume behavior, and failure matrix.

## Scientific source rules

- **Charts:** use actual CSV headers and rows. No invented series, interpolation disguised as source data, or label-based guessing. The chart mapping records raw cells, numeric values, and CSV line numbers; the report compares every plotted value with its parsed primary-source cell.
- **Biological `figure03`:** inspect the actual PDF page/render or supplied figure. Record page/region, source ID/version, observed entities, visible relationships, ambiguous labels, and uncertainties in `figure_inspection`. A plausible biological mechanism cannot substitute for inspection. The runner preserves these observations but does not claim that SVG export verifies biology.
- **Existing SVG edits:** use `svg_edit` literal, counted replacements with an expected match count. The runner patches only those substrings, leaves the original input untouched, records before/after hashes, and does not pretty-print, restyle, rasterize, or rebuild the SVG.
- **New diagrams:** the built-in layout is deliberately modest. Source correctness and explicit ambiguity records take priority over decoration.

## Degradation and resume

Missing files, unreadable files, multiple/conflicting matches, unavailable export software, and invalid semantics are respectively `missing_material`, `unreadable`, `ambiguous`, `tool_unavailable`, and `semantic_defect`. Do not collapse them into a generic failure. If PNG or PDF export is missing, fails, or returns a structurally invalid file, the SVG, manifest, report, checkpoint, and atomically written result survive. Only the affected preview is unavailable; a requested missing preview makes the result `partial` and the process exits 2. Export reports in the checkpoint and Markdown report retain per-format attempts, exporter availability, validation, and reuse. A malformed case exits nonzero while retaining an honest `result.json` when the output directory is writable.

PNG export uses installed rsvg/Inkscape/ImageMagick/`sips`/CairoSVG as supported. PDF export uses installed rsvg/Inkscape/Chrome/Chromium/CairoSVG. Candidates are attempted without installation until one succeeds; module presence alone is not called a successful CairoSVG export. PNG signature/IHDR/dimensions/IEND are checked. PDF validation checks the header, final `startxref`/`%%EOF`, the xref target, catalog `Root`, and a page object. These checks establish real file structure, not scientific or visual fidelity.

Resume after fixing the actual source or specification:

```bash
python3 /skills/weekly-skill/scripts/case_runner.py \
  --case /input/case.json \
  --spec /app/work/case_spec.json \
  --work-dir /app/work --output-dir /app/output \
  --preview-png --resume
```

Intake and validation always rerun. Intact render/export artifacts are reused only when their previous stage succeeded and the fingerprint of actual source hashes, runner, contract, independent PNG/PDF requests, and preview exporter override matches. Cached PNG/PDF structure is revalidated before reuse; a corrupt preview is exported again rather than trusted. Changed inputs or either preview request invalidate stale contracted artifacts. Report and result are rebuilt on every run. No package installation, hidden answer, benchmark score, timestamp, or unbounded retry is used. Chrome/Chromium export is headless on the local SVG file with background networking disabled.

## Runnable synthetic interface check

The included example is explicitly **SYNTHETIC**, has no official scientific answer, and demonstrates unusual contract-key projection:

```bash
python3 /skills/weekly-skill/scripts/run_example.py \
  --example-dir /skills/weekly-skill/examples/synthetic \
  --output-dir /app/work/synthetic-output \
  --preview-png
```

It produces `figure.svg`, `data_mapping.json`, `result.json`, `manifest.json`, `checkpoint.json`, and `report.md`; with a detected exporter and `--preview-png` it also produces `figure.png`. The unusual-key contract remains unchanged. Adding `--preview-pdf` demonstrates a separate auxiliary `preview.pdf` without adding a synthetic contract key; official PDF contracts instead use their declared dynamic key and `pdf_artifact_key` in the specification. Exit 0 means success, 2 means honest partial, and 3 means case-level failure. For a no-install negative check, setting `RESILIENT_CASE_PREVIEW_EXPORTER=none` simulates exporter absence for either format and must preserve SVG/result while returning partial when that format was requested. Other supported values name an already installed exporter executable or `cairosvg`; absence or export failure is detected rather than repaired.
