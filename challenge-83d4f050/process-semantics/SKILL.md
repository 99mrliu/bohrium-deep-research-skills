---
name: process-semantics
description: Model, audit, and render SBGN-inspired processes with explicit inputs, outputs, compartments, and modulator effects. Use when mechanism diagrams must distinguish consumption and production from activation arrows and inhibition T-bars without equating binding, transport, stimulation, or modification.
---

# Process Semantics

This Skill makes the **process node and its arcs** the primary model. Entity identity is only an addressable endpoint. Glyph generation and validation consume the same semantic JSON; neither a picture nor a process name can silently change a relation.

## Formal run contract

```bash
python3 scripts/process_semantics.py run \
  --input-dir /input --work-dir /app/work --output-dir /app/output
```

The runner reads `/input/case.json`, `/input/task.md`, and `/input/figure-workorder.json` (also accept `/input/artifacts/figure-workorder.json`). Because `/input` is authoritative and may be read-only, copy needed inputs to `/app/work/staged`, preserve original `case_id` and full `output_contract`, and add the curated `model` only to the staged case; run with `--input-dir /app/work/staged`. Keep original source paths and hashes in the result. It inventories the complete input tree, extracts text (not claims) from paper PDFs with PyMuPDF, reads `figure03*` original/caption text files, and inventories CSV/TSV/JSON data. Put the original at `input/figure03.svg` (preferred), its caption at `input/figure03.caption.txt`, real data under `input/data/`, and papers under `input/papers/`. Optional exact input paths may also be listed in `case.source_files`. A supplied SVG source is retained in `work/original/`, its XML subtree is preserved, and a generated semantic layer is appended.

`case.model` contains `entities` and `processes`, as specified in [references/process-schema.md](references/process-schema.md). Required transport fields are explicit. Input JSON is the sole source of biological relations. **No paper text, model prior, association, or label heuristic silently adds a process or arc.** Read [references/sourcing-and-export.md](references/sourcing-and-export.md) before production.

The runner writes `/app/output/result.json` in a minimal `partial` state immediately after reading the case. Final `result.json` dynamically contains every field declared in `case.output_contract`, including unrecognized custom fields (null when no built-in value exists). Normal fields are `case_id`, `status`, `editable_source`, `export_artifact`, `content_map`, `compliance_checks`, `exceptions`; `sources`, `uncertainty`, and `change_records` are always added. `success` requires validation, SVG generation, and PNG/PDF export. Validation/export exhaustion returns 2 with `partial`; fatal input errors return 1 with `failed`. A previously written output never constitutes success.

Outputs include `editable_source.svg`, `export.png`, `export.pdf`, `process-model.json`, `semantic-audit.json`, `content-map.json`, and `result.json`. Python 3 standard library code generates SVG; PyMuPDF exports PNG/PDF (`pymupdf`, legacy `fitz` fallback). No network is needed or used.

## Rules enforced before drawing

- A process is one of `association`, `dissociation`, `phosphorylation`, `ubiquitination`, `transport`, `transcription`, `activation`, `inhibition`, or `uncertain`.
- Every process explicitly contains `inputs`, `outputs`, and `modulators`, and has at least one input or output. Every endpoint must exist.
- Inputs use filled consumption arrows; outputs use filled production arrows. Modulator activation uses a hollow stimulation arrow, inhibition a perpendicular T-bar, and uncertainty a dashed question-mark line. These are separate arc classes.
- An inhibition process must have no outputs and can never emit a production arc. Binding/association does **not** create activation.
- Transport requires distinct nonempty `from_compartment` and `to_compartment`, at least one input and output, and consistent declared entity compartments.
- A modulator effect must be `activation`, `inhibition`, or `uncertain`; its arc targets the process node, never an unnamed edge ambiguity.

See [references/process-schema.md](references/process-schema.md) for the full contract and [references/sourcing-and-export.md](references/sourcing-and-export.md) for source preservation/export limits.

## Runnable SYNTHETIC demonstration

All examples are **SYNTHETIC — NOT A SCIENTIFIC CLAIM**. From this bundle directory:

```bash
python3 scripts/process_semantics.py demo --destination /tmp/process-semantics-validation
# Expected success: 0; deliberate illegal inhibition production: nonzero.
```

The success fixture displays receptor-stimulated kinase activation, an inhibitor T-bar, and distinct-compartment transport. The failure fixture deliberately gives an inhibition process an output, and also uses an inseparable transport route. Manual commands:

```bash
python3 scripts/process_semantics.py run --synthetic \
  --input-dir examples/synthetic/input --work-dir /tmp/ps-work --output-dir /tmp/ps-output
python3 scripts/process_semantics.py run --synthetic \
  --input-dir examples/synthetic-failure/input --work-dir /tmp/ps-fail-work --output-dir /tmp/ps-fail-output
```

Production inputs must have `"synthetic": false`; `--synthetic` must not be used to relabel real work. Toy labels and source locators are not biological conclusions.

## Limits

Validation establishes representational consistency, not scientific truth. The process vocabulary is SBGN-inspired rather than a claim of full SBGN XML/PD interoperability. PDF text is retained for provenance/review, not machine-extracted science. Automatic layout is intentionally small and deterministic; a curator may need to adjust layout without changing the semantic JSON.
