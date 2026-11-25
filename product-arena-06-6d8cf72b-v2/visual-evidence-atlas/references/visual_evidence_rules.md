# Visual-evidence record and review rules

## Atlas document

The validator accepts UTF-8 JSON with these top-level keys: `schema_version`, `case_id`, `synthetic`, `coordinate_convention`, `pages`, `crops`, `regions`, `visual_claims`, and `change_records`. Optional `task_answer` provides the direct answer used by the demonstration builder. No source statement may be inferred from an asset's filename.

Each page contains:

- `page_id`, `pdf_page_index`, nullable `printed_page`;
- `source_file`, the actual source identity as recorded by the agent; the pair `(normalized source_file, pdf_page_index)` must be unique. Main and supplemental PDFs have independent sequences and may both use index 0;
- `image`: `path`, integer `width` and `height`, and `role` such as `original_page_render` or `original_synthetic_page_fixture`;
- `layout`: integer `columns` and `reading_order` (`certain` or `uncertain`), plus a note.

Each crop contains a unique `crop_id`, `page_id`, `parent_region_id`, `source_bbox` in original page coordinates, and an `image` with `path`, crop-pixel `width`/`height`, and original-crop role. The source bbox and asset existence are checked; crop enlargement never changes the coordinate convention. The crops array may be empty when no crop is task-relevant.

Each region contains `region_id`, `page_id`, `kind`, and `bbox`. Optional fields are `parent_id`, `panel_label`, `row_label`, `column_label`, `evidence_state`, and `text_evidence`. `text_evidence` has `role` and nullable `source_anchor`. Caption, body_paragraph, and table_cell regions must have checked source anchors. `evidence_state` keeps `available`, `missing`, `unreadable`, `not_reported`, and `conflict` distinct.

Every change record contains a unique `change_record_id`, `actor`, `action`, `subject_ids`, and `note`. A visual attestation uses action `visual_inspection_attestation`, names its claim in `subject_ids`, and explains what original render/crop the agent actually inspected. An attestation is provenance, not machine-verified truth.

## Decisive visual claims

Each claim contains:

- unique `claim_id`, `claim_text`, boolean `decisive`, and nonempty `subject_region_ids`;
- `inspection.status`: `agent_attested_inspected`, `not_inspected`, `missing`, or `unreadable`;
- `inspection.change_record_id`: required for attested inspection, otherwise null;
- `caption_corroboration` and `body_corroboration`, each with `state` and `source_anchor`.

Corroboration states are `corroborated`, `not_reported`, `conflict`, `missing`, and `unreadable`. A machine can check anchor consistency and required states, but cannot verify that pixels support a proposition. The audit therefore always sets `machine_visual_truth_verified` to false.

Resolution is deterministic:

1. A subject region whose `evidence_state` is conflict, missing, unreadable, or not_reported makes the claim `unresolved_<state>`. The named subject IDs stay in the reason; a decisive claim cannot become `reviewed_corroborated` or disappear from the audit's unresolved warnings.
2. If either corroboration is conflict, missing, or unreadable, that exact state remains unresolved.
3. Direct table-cell evidence requires agent-attested inspection of an available original `table_cell` plus verified nonempty row and column labels (and consistency with a row/column parent when one is supplied). Such a claim is `reviewed_corroborated` even when body text is not_reported: direct pixel/cell evidence is not caption-only. Absent body corroboration produces a non-unresolved limitation warning, preserving an overall partial status without discarding the direct evidence.
4. `unresolved_caption_only_cell` is reserved for an individual cell with corroborated caption and not-reported body when the cell was not agent-attested inspected or its row/column identity is unclear. Caption evidence alone never supplies the missing inspection or identity.
5. Otherwise, if a claim is not agent-attested, it is unresolved with its missing/unreadable/not-inspected state; other not_reported corroboration also remains unresolved.
6. Only an attested claim with both caption and body corroborated, or the direct-cell case above, and none of the preceding issues is `reviewed_corroborated`; this still is not machine-verified visual truth.

Nondecisive context follows the same state reporting, but does not by itself force result status partial. Any error makes validation fail. Warnings make the demonstration result partial; unresolved decisive subject-region or corroboration states always generate warnings.

## Evidence preservation and special failures

Original page renders and original crops are evidence artifacts. Save them in the output evidence area and link them without data-URL embedding. HTML is self-contained in logic and styling, with no remote dependencies; local original image files remain separate evidence. Do not generate substitute charts. SVG is allowed in the fictional bundle solely as a labelled original synthetic page fixture.

A page render that cannot be produced is `missing` when absent and `unreadable` when access, encryption, permission, decoding, or resolution prevents inspection. Text not present in caption/body is `not_reported`. Disagreement among source anchors or between attested visual evidence and text is `conflict`. OCR errors remain explicit. None of these states may be silently converted into a passing corroboration.

For vector artwork, rasterize and look at the original rendered page. For multi-panel figures preserve panel labels and crop parentage. For supplements use their own file and PDF/printed page identity. For double-column pages expose reading-order uncertainty. No validator result can substitute for actual agent sight.

## Audit and result

The audit contains errors, warnings, unresolved claims, and the machine-visual-truth disclaimer. The example builder also validates a JSON Schema subset: object/array/string/integer/number/boolean/null types, required properties, enum, const, minItems, and `additionalProperties: false` recursively. Unknown schema keywords are rejected rather than silently ignored. A malformed atlas or closed-contract violation exits nonzero.

Use the CLI shown in SKILL.md. `validate` always attempts to write its audit; `render` and `build` stop on errors. The HTML and Markdown include image links, coordinates, identities, corroboration, inspection attestations, and unresolved items. Read both outputs back after generation.
