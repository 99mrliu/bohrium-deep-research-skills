---
name: observation-graph
description: Build a document-to-extraction-to-observation identity graph for literature-data cleaning, conservatively adjudicate duplicates with explicit allow/deny certificates, retain all rows, and exclude only certified transport duplicates from statistical views.
---

# Observation Identity Graph

Challenge: **challenge-f4bca185 — 文献数据清洗与标准化**.

The center of this Skill is **observation identity**, not unit conversion. A measurement extracted twice, an experiment run twice, and two measurements made under different conditions are not transport duplicates. Equal values never erase conflicting context.

## Trigger

Use when a task asks to clean, reconcile, deduplicate, audit, or statistically summarize literature extraction rows and one or more apply:

- document, extraction, experiment, sample, material, metric, or condition identity matters;
- repeated rows may be transport copies, repeated extraction, or repeated experiments;
- a proposed merge must be justified and rejected candidates must remain reviewable;
- every original row must survive in cleaned output;
- the task supplies an observation/row identity contract or explicit duplicate IDs.

## Do not trigger

Do not use this Skill as the primary solution for:

- unit conversion, numeric parsing, chemical-structure inference, or property prediction alone;
- deleting near-identical text without observation context;
- entity resolution based on chemical similarity or guessed synonyms;
- a task with no duplicate/identity adjudication component;
- replacing human review of conflicting or unresolved identities.

Minimal whitespace/numeric-spelling normalization and case-declared synonyms are supported, but they do not authorize a merge.

## Required runtime

Python 3 standard library only. No network, credentials, submission, Git operation, random seed, clock, non-deterministic identifier, `NaN`, or `Infinity` is used.

Entry point:

```sh
python3 scripts/observation_graph.py \
  --input /input --work /app/work --output /app/output \
  --case /input/case.json --task /input/task.md
```

Defaults are `--input /input`, `--work /app/work`, and `--output /app/output`. `--case` and `--task` are optional; auto-detection checks `case.json` then `case.jsonl`, and `task.md`, `task.json`, then `task.jsonl`. JSON metadata is read; Markdown task text is hashed and retained without being treated as a JSON rule declaration. A supplied relative metadata path is resolved against `--input`; an absolute path is also accepted. An explicitly supplied missing path is an input error.

The process creates an early `result.json` with `status="partial"`, then replaces its content with the final deterministic JSON document. The work directory contains no cache required for correctness.

## Input contract

Read the actual case/task metadata and all non-metadata `.csv`, `.tsv`, `.json`, and `.jsonl` materials recursively beneath the input directory. CSV delimiter sniffing is limited to comma/tab; TSV is tab-delimited. JSON Lines may be blank-line separated and is processed in file line order.

Common wrappers are supported: `rows`, `data`, `records`, `observations`, `materials`, `items`, `documents`, `extractions`, and `results`. Document/extraction scalar attributes are inherited by child observations. Single-object wrappers such as `{"case": {...}}`, `{"task": {...}}`, and `{"data": [...]}` are unwrapped.

Common field aliases are recognized for observation, duplicate group, document, extraction, experiment, sample, material, metric, value, and unit. Original keys and values are retained in cleaned rows. Source filename and source row are always attached.

A case must provide `case_id` (or `id`) and at least one observation object, either in an external material or a common embedded case record container. Missing metadata, empty materials, malformed JSON/JSONL, non-finite JSON numbers, or an explicitly missing metadata file produce nonzero exit status and empty, honest managed outputs with `status="input_error"`.

### Case-declared identity contract

Preferred configuration:

```json
{
  "case_id": "case-specific-id",
  "identity_contract": {
    "row_id_field": "observation_id",
    "identity_fields": ["observation_id"],
    "candidate_identity_fields": ["observation_id", "duplicate_group"],
    "transport_fields": ["observation_id", "document_id", "sample_id", "material", "metric", "value", "unit"],
    "condition_fields": ["temperature", "pressure", "solvent"],
    "allow_exact_transport_duplicates": true
  },
  "synonyms": {
    "material": {"Preferred Label": ["Declared Alias"]}
  }
}
```

`identity_contract`, `row_identity`, `identity`, and `duplicate_policy` are accepted as contract containers. Scalar/list forms of identity fields are accepted. `auto_deduplicate: true` is accepted as the explicit authorization alias, but by itself does not weaken the normalized-raw-equality requirement.

If no enabling declared contract exists, **no automatic deduplication occurs**, even for byte-equivalent rows. Such candidates are unresolved. Missing values are data, not wildcards. Condition fields include declared fields, known condition aliases, nested `conditions` objects, and every `condition_`/`condition.` key. The fingerprint covers the complete canonical condition mapping.

Synonyms are used only from the case-declared map. Matching is exact after whitespace/case folding or token-aware by sorted Unicode word tokens. There is no formula parsing, chemical-name expansion, abbreviation invention, or similarity guess.

## Graph and adjudication contract

Nodes explicitly model `document`, `extraction`, and `observation`. `EXTRACTED_FROM` and `OBSERVED_IN` connect them. Observation nodes carry source/sample/material/metric/value/unit, full conditions and fingerprint, disposition, cluster ID, and statistical inclusion.

Context edges are explicit:

- `SAME_EXTRACTION`: same declared extraction ID;
- `SAME_SAMPLE`: same declared sample ID;
- `SAME_CONDITION`: same full condition fingerprint for the same sample/material/metric core;
- `SAME_EXPERIMENT`: same declared experiment ID.

These edges do **not** authorize merging. Only `CERTIFIED_TRANSPORT_DUPLICATE`, linked to an allow-certified decision, affects cluster membership and statistical inclusion.

Candidate blocks use each declared row/duplicate identity field independently, source+sample+material+metric, sample+material+metric+full-condition fingerprint, the broader sample/material/metric core, and experiment+material+metric. Blocking creates candidates, not merge decisions.

Decision classes are exactly:

1. `exact_transport_duplicate` — merge allowed only under the case identity contract;
2. `repeated_extraction` — retained separately;
3. `repeated_experiment` — retained separately;
4. `same_core_different_context` — retained separately;
5. `conflicting_identity` — retained separately and queued at high priority;
6. `unresolved` — retained separately and queued at high priority.

Every candidate receives one decision. Each proposed merge has an `allow` certificate. Every rejected candidate has a `deny` certificate naming all detected `mismatching_fields`; an empty mismatch list means insufficient evidence, not proof of equality. See [graph semantics](references/graph-semantics.md) and [certificates](references/certificates.md).

## Output contract

The output directory always contains:

| File | Contract |
|---|---|
| `cleaned.csv` | Every input observation row, original columns plus graph/disposition metadata; no semantic deletion |
| `cleaned.json` | All rows plus a `statistical_view` excluding only allow-certified transport duplicates |
| `observation_graph.jsonl` | One graph node or edge per line, deterministic IDs and explicit evidence |
| `duplicate_decisions.jsonl` | One allow/deny-certified adjudication per candidate pair |
| `changes.jsonl` | Declared synonym changes and transport-only statistical exclusions |
| `review_queue.csv` | Every rejected candidate; conflicts/unresolved need review, contextual classes are informational |
| `audit.md` | Identity contract, counts, categories, statistical rule, and uncertainty |
| `result.json` | Machine-readable status, provenance, artifacts, changes, review queue, and contract fields |

Added cleaned-row fields are `_observation_node_id`, `_disposition`, `_cluster_id`, `_statistical_include`, `_condition_fingerprint`, `_source_file`, and `_source_row`. The CSV boolean is true for every representative and false only for another row in an allow-certified transport component. No repeated extraction, repeated experiment, context mismatch, conflicting identity, or unresolved row is excluded from the statistical view.

`result.json` always includes `case_id`, `status`, `sources`, `uncertainty`, `change_records`, `review_queue`, `artifacts`, and `unresolved_required_fields`. For every top-level key in `output_contract` (dictionary, list of names, field-object lists, or `fields`/`properties`/`outputs` wrappers), the same key is emitted in `result.json`. Base fields such as `status` and `sources` retain their computed values rather than being overwritten. Known artifact requests receive path/count descriptors; cleaned-data and change-data requests receive their actual JSON arrays. Unknown required keys are `null`, named in `unresolved_required_fields`, accompanied by uncertainty, and make final status `partial`. Completed known contracts use `success`; invalid cases use `input_error` and exit 2.

## Execution protocol

1. Read case/task and establish the declared identity contract before normalizing materials.
2. Write the early partial result.
3. Load observations with source provenance and construct complete condition fingerprints.
4. Build document/extraction/observation nodes and candidate blocks.
5. Adjudicate every candidate and issue an allow or deny certificate.
6. Connect only certified transport duplicates into merge components.
7. Write all rows, graph, decisions, changes, review queue, and statistical view.
8. Validate certificate/action consistency, row retention, contract coverage, deterministic bytes, and finite JSON before reporting completion.

## Synthetic example

`examples/synthetic-input` and the genuinely generated `examples/synthetic-output` are marked `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`; neither is an official competition case. Run:

```sh
sh examples/run.sh
```

The example demonstrates exact transport duplication versus repeated experiment, repeated extraction, same-core/different-condition, conflicting explicit duplicate IDs, and unresolved evidence. Output files are regenerated in place; rerun byte comparisons are deterministic.

For safe modifications and regression checks, see [maintenance](references/maintenance.md).
