---
name: claim-evidence-cartographer
description: Curate auditable paper claim–evidence graphs that separate current-author conclusions, limitations, hypotheses/speculation, methods/observations, and prior-work/cited claims. Use for literature conclusion-and-data extraction when hedges, modalities, quantitative support, experimental conditions, comparator context, exact source locations, and every requested target field must survive without upgrading inference or citation to fact.
---

# Claim–Evidence Cartographer

## Purpose and boundary

Build a **source-grounded discourse graph**, not a keyword-frequency table or a prose summary. A number becomes a field value only through a curated observation linked to its experimental conditions and comparator. A statement becomes an author conclusion only through current-author discourse and attribution evidence. `supported_by` means “offered as support by the authors,” never “proved.”

This skill is strongest when an agent can read the actual paper and write explicit curation JSON. The scripts mechanically register text, validate exact quotations and provenance, assemble target-field records, and render the graph. They **do not automatically infer scientific meaning, extract numbers by keywords, or verify that a cited original really supports the current authors' paraphrase**.

## Non-negotiable reading rules

1. Read `/input/case.json`, `/input/target-fields.json`, `/input/task.md`, and every supplied paper/artifact relevant to the request. Actual inputs override labels and filenames.
2. Preserve all target `field_id`s and request order. Emit one record in both `result.fields` and its identical mirror `result.field_results`. Never leave a requested field out.
3. Use the five discourse kinds exactly: `author_conclusion`, `limitation`, `hypothesis_speculation`, `method_observation`, `prior_work_cited_claim`.
4. Preserve operative hedges (`may`, `might`, `could`, `suggests`, `we speculate`, `not tested`, and source-specific equivalents) as literal strings in `hedges` and in verbatim evidence. Do not silently turn correlation, proposed mechanism, or possibility into causation or fact.
5. Attribution is part of meaning. “X et al. reported/showed…” belongs to `prior_work_cited_claim` even if it occurs in the abstract or discussion. The current study's result and a cited comparator must be different observations.
6. Quantitative observations link to a condition node. Resolve “under these conditions,” table headers, footnotes, figure captions, and supplementary cross-references before binding values. Preserve original scalar, units, statistic/error, and comparator; do not convert, average, recombine, or infer missing precision.
7. Every quotation must be copied verbatim from a registered paragraph. Every `source_id`, `paragraph_id`, and optional page must already exist in `sources.json`. Never invent a quotation, paragraph, page, table, citation, DOI, or metadata field.
8. `not_reported` means the defined source scope was read and the field is absent or explicitly unknown; it does not mean zero, no effect, or extraction failure. Use `extraction_failed` when the source may contain it but available text/tools could not reliably recover it. Use `source_conflict` when incompatible source values remain, exposing both locations rather than silently choosing one.

See [references/discourse-rules.md](references/discourse-rules.md) before classifying claims.

## Runtime workflow

Run from any working directory. Set `SKILL_DIR` to the installed directory containing this `SKILL.md`; the commands use no author-local paths. Python 3.8+ standard library is sufficient for curation and validation. Mechanical PDF text extraction optionally invokes the system `pdftotext` if present; there are no third-party Python dependencies.

### 1. Initialize and save an honest partial immediately

```bash
python3 "$SKILL_DIR/scripts/prepare_case.py" \
  --input /input --work /app/work --output /app/output
```

This first writes `/app/output/result.json` with every requested field as `extraction_failed`, null scalar, and a pending-curation explanation. Those placeholders are not answers. It then:

- discovers actual paper/artifact files under `/input`;
- writes `/app/work/sources.json` and paragraph-indexed text under `/app/work/source-text/`;
- records PDF/text failures in `/app/work/ingestion-warnings.json`;
- writes `/app/work/curation-template.json` and, once only, `/app/work/curated.json`;
- preserves an existing early result unless `--reset` is explicitly requested.

Do not use `--reset` after real curation unless replacement is intended. If a readable text layer is unavailable, visually inspect/OCR with available runtime tools or retain `partial`/`insufficient_evidence` with a precise handoff location. Do not claim to have read inaccessible pages.

### 2. Read, construct the ledger, then curate

Read `/app/work/task.md`, the target questions, and **all** registered source text. When paper rendering tools are available, inspect original pages, tables, captions, and supplements as needed; extracted line order alone can misrepresent merged cells. Add no factual content from domain priors.

In `/app/work/curated.json`, create nodes in this order:

1. **Conditions:** sample/material, setting, temperature, duration, pressure, data source, time point, measurement method, and other applicability qualifiers actually stated. Use multiple evidence items when the condition spans paragraphs.
2. **Observations:** current methods, qualitative observations, and quantitative results. For current values keep `scalar`, `units`, `statistic`, `comparator`, `condition_ids`, and evidence together. Cited values must be identified as cited in the linked claim/notes.
3. **Claims:** discourse kind, exact attribution origin, epistemic status, modality, hedges, supporting observation IDs, condition IDs, and evidence. Use `promotion_allowed: false` for hypotheses, cited claims, and limitations.
4. **Field results:** map each target to observation and/or claim IDs. Observation-backed numeric fields inherit scalar, units, statistic, comparator, and conditions from the observation; edits that disagree with the linked observation are rejected. Claim-only qualitative fields provide an explicit scalar prefixed/labeled with the true epistemic layer.
5. **Uncertainties:** unexamined sources, unresolved cross-references, extraction problems, missing cited originals, and conflicts. Do not use notes to hide an unsupported assertion.

The complete curation schema and status rules are in [references/curation-schema.md](references/curation-schema.md). For time-sensitive work, save valid subsets incrementally; unsupplied targets automatically remain `extraction_failed`, producing an honest partial.

### 3. Generate deliverables

```bash
python3 "$SKILL_DIR/scripts/build_graph.py" \
  --case /input/case.json \
  --targets /input/target-fields.json \
  --sources /app/work/sources.json \
  --curated /app/work/curated.json \
  --output /app/output
```

On success this actually generates:

- `/app/output/result.json` — required response contract, all fields, claims, uncertainties, sources, and change record;
- `/app/output/graph.json` — case, source, paragraph, condition, observation, claim, and target-field nodes; directed support/scope/evidence edges;
- `/app/output/evidence-map.md` — readable field table plus layered claims, values, conditions, quotations, and uncertainties.

The builder fails before replacement output when a quote/location is invalid, a linked value changes, a conflict is silently resolved, or a guarded claim is promoted. The earlier honest partial remains available if a runtime failure interrupts improvement.

### 4. Independently validate and inspect

```bash
python3 "$SKILL_DIR/scripts/validate_result.py" \
  --result /app/output/result.json \
  --graph /app/output/graph.json \
  --targets /input/target-fields.json \
  --sources /app/work/sources.json \
  --report /app/output/validation.json
```

Then open the JSON and Markdown, not just the exit code. Compare a sample spanning abstract, results, tables/captions, and supplement against the original. Check that:

- scalar ↔ units ↔ statistic ↔ condition ↔ comparator all describe the same entity and run;
- primary `paragraph_id`/`quote` identify the value or claim, while condition evidence can add other paragraphs;
- each hedged/cited/scoped claim still has its attribution and modality in result and map;
- `experimental_condition` and `condition` are equal;
- every requested field appears exactly once in both mirrors with one allowed per-field status;
- `extraction_failed`, `not_reported`, and `source_conflict` have not been collapsed;
- the run status honestly reflects unresolved fields; claims and uncertainty arrays agree with the graph.

If validation fails, fix the **curation or source registration**, never fabricate a source span to satisfy the checker. Full contract and triage guidance: [references/runtime-contract.md](references/runtime-contract.md).

## Status semantics

Per field: `reported | not_reported | source_conflict | extraction_failed`.

Top level:

- `answered`: every target has a completed adjudication (`reported`, scoped `not_reported`, or documented `source_conflict`); this says requested fields were answered, not that all author claims are true.
- `partial`: at least one field remains `extraction_failed` while at least one requested value is reported.
- `insufficient_evidence`: no requested value can be reported, or every requested field is explicitly `not_reported` after source review.
- `input_error`: required case/target input is missing, malformed, or has duplicate IDs.

A partial or insufficient result names exactly what remains and where human review should resume. A completed graph can legitimately be `insufficient_evidence`, as the negative example demonstrates.

## Synthetic runnable examples

All files under `examples/` are explicitly **SYNTHETIC**, are not formal cases, and contain no hidden/benchmark answers. The minimal example supplies paragraph JSON and plain text, `case.json`, `target-fields.json`, task text, curated observations/conditions/claims, and generated `graph.json`, `result.json`, `evidence-map.md`, and `validation.json`.

Regenerate and test both examples from the bundle root:

```bash
python3 scripts/run_examples.py
python3 scripts/self_test.py
```

- `examples/minimal/`: four targets, five discourse kinds, two quantitative current observations, cited quantitative context, complete condition binding, an untested hypothesis, and explicit non-reporting beyond 6 h.
- `examples/negative/`: a cited sentence with `could`/`might` and “did not test” remains `prior_work_cited_claim`; the requested established current-author mechanism is `not_reported` with null scalar. `invalid-promotion.json` deliberately relabels it as an author conclusion and must fail with `NEGATIVE-PROMOTION-GUARD` before generating output.
- `examples/minimal/INSPECTION.md`: actual run observations and checked artifacts, not claimed benchmark performance.

To run only the minimal build, substitute its paths into the build/validate commands and use `--output examples/minimal/output`.

## Limitations and maintenance

- Mechanical `pdftotext` output can be incomplete or have bad reading order; scanned PDFs need OCR/visual reading. The initializer reports rather than disguises this. Complex tables require source-aware human/agent reconstruction.
- The validator verifies exact substrings, schema, linkage consistency, and explicit provenance guards. It cannot prove a paraphrase is semantically faithful, establish absence beyond the documented scope, or detect every subtly erased modality. Final scientific inspection remains necessary.
- Citation metadata and cited-paper claims are not independently verified unless the cited source is supplied and read. Keep “as cited” attribution otherwise.
- Update examples and rerun both test commands after modifying schemas or guards. Keep all inputs and examples UTF-8 text and the bundle dependency-free.
