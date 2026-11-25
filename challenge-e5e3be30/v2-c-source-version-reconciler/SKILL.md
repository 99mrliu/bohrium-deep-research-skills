---
name: source-version-reconciler
description: Reconcile source identity across preprints, revisions, versions of record, corrections, retractions, and supplements; bind every quotation to one immutable document version, validate the source-version DAG, and issue version-scoped four-level verdicts without pooling versions into false evidence. Use when claims depend on which source version said what, when files may be duplicates, or when supplemental evidence must not inherit main-text identity or pagination.
---

# Source Version Reconciler

## Purpose and non-goals

Determine **which immutable document/version supports which part of each claim**. Keep preprint v1, revised v2, publisher version, correction, retraction, and supplement distinct unless exact source evidence establishes their relation. Preserve version differences in parallel. Never pool quotations, results, denominators, or support across versions, and never assume that the newest version wins.

This is not generic conflict arbitration, citation-style verification, or report rendering. The central artifacts are the source inventory, reviewed immutable-document identities, source-version DAG, single-version evidence bindings, version matrix, and scoped verdicts.

Treat `claims-to-verify.json` as a list of hypotheses, **not facts**. Topic relevance is not support; an unreported proposition is not refuted.

## Runtime contract

The challenge environment provides:

- Skill root: `/skills/weekly-skill`.
- Input: `/input/case.json`, `/input/task.md`, `/input/claims-to-verify.json`, and actual source materials.
- Writable work directory: `/app/work`.
- Required final result: `/app/output/result.json`.

Complete the work within the challenge's 900-second budget and 64-request limit. Local Python commands are deterministic and require no network, downloads, package installation, or model requests. Reserve time to validate and read back the final output. If data or time is incomplete, leave an honest `status: "partial"` with explicit uncertainty; do not manufacture a complete answer.

The final top-level object must contain:

1. `case_id`, copied exactly from `/input/case.json`.
2. **Every field in `case.output_contract`**, preserving whether each field is a list or object. Do not hardcode one case's contract.
3. `status`: `partial` or `complete`.
4. `sources`: immutable `document_id` records with identity/version and actual hashes.
5. `uncertainty`: unresolved identities, unreadable sources, invalid or absent evidence, impossible comparisons, and limitations. Use an empty list only if no material uncertainty remains.
6. `change_records`: chronologically ordered initialization, inventory, metadata, evidence, and finalization records.

Claim statuses are exactly `supported`, `partially_supported`, `contradicted`, or `insufficient_evidence`.

## Mandatory workflow

### 1. Read the contract and write partial first

Read task, case, and claims before judging any source. Then immediately initialize the result. This protects the required dynamic skeleton if a later stage fails.

```bash
python3 /skills/weekly-skill/scripts/reconcile.py init \
  --input /input \
  --output /app/output/result.json
```

The initializer copies `case_id`, creates every `output_contract` field with the declared container kind, seeds unverified claims as `insufficient_evidence`, and writes `status: partial`, empty sources, uncertainty, and a change record. Read this file back if time is critical. Do not await source analysis before creating it.

### 2. Hash actual materials; inventory is not identity metadata

```bash
python3 /skills/weekly-skill/scripts/reconcile.py inventory \
  --input /input \
  --output /app/work/source-inventory.json
```

The command recursively inventories actual material files and excludes only root control files `case.json`, `task.md`, and `claims-to-verify.json`. It computes SHA-256 over bytes, size, text readability, and `duplicate_of`. `duplicate_of` means same bytes only—not independent corroboration and not proof that two non-identical versions are equivalent.

Symlinked input is rejected rather than followed. UTF-8 text can be quote-checked directly. Other formats are hashed but have no built-in text extractor. Do not pretend to have read an unreadable PDF or page image; either supply a separately verified text extraction as a material with explicit provenance or retain `insufficient_evidence` and explain the limitation. Do not install an extractor merely to force a verdict.

### 3. Review and write immutable source metadata

Inspect the actual documents and create `/app/work/reviewed-source-metadata.json` using this shape:

```json
{
  "documents": [
    {
      "document_id": "doc-main-v1",
      "title": "Exact title or null",
      "doi": null,
      "version": "v1",
      "date": "Source-stated date or null",
      "kind": "preprint",
      "files": ["actual/relative/file-v1.txt"],
      "relations": []
    },
    {
      "document_id": "doc-main-v2",
      "title": "Exact title or null",
      "doi": null,
      "version": "v2",
      "date": null,
      "kind": "preprint_revision",
      "files": ["actual/relative/file-v2.txt"],
      "relations": [{"type": "revises", "target_id": "doc-main-v1"}]
    }
  ]
}
```

Rules:

- A `document_id` means **one immutable version**, not a work family or floating latest version. Use deterministic descriptive IDs made from ASCII letters, digits, `.`, `_`, and `-`.
- `files` contains inventory `file_id` values relative to `/input`. Multiple files may share one document only if their hashes match exactly, as with duplicate copies. A file cannot be assigned to multiple document/version IDs.
- Enter DOI, title, version, and date only when source inspection supports them. Unknown values are `null`; do not guess from a filename or similarity.
- Include corrections, publisher versions, retractions, and supplements as their own document nodes. Do not attach supplemental files to the main document as interchangeable copies—their hashes and content differ.
- Use only source-supported relations: `revises`, `corrects`, `supplements`, `retracts`, `version_of`, or `related_to`. Every target must exist. Relation is a source assertion, not a reason to rank the newer version as true.
- Inspect unassigned inventory files. Either account for relevant material or document in uncertainty why it remains unused.

### 4. Validate identity bindings and the DAG before claims

```bash
python3 /skills/weekly-skill/scripts/reconcile.py validate \
  --input /input \
  --work /app/work \
  --metadata /app/work/reviewed-source-metadata.json
```

This rehashes bound files, detects stale inventory, verifies one digest per immutable document, checks file/version uniqueness, rejects dangling relations, detects cycles including self-cycles, and writes `/app/work/source-version-dag.json` only for an acyclic graph. Any validation failure exits `1`. Stop finalization, revisit the explicit source evidence, and correct only demonstrable metadata errors. Never remove a real relation merely to force the DAG to pass; if identity remains unresolved, retain partial output and record uncertainty.

### 5. Bind evidence one document/version at a time

Create `/app/work/reviewed-evidence-map.json` after directly examining each scoped version:

```json
{
  "claim_decisions": [
    {
      "claim_id": "claim-from-input",
      "rationale": "What each version says, why that entails or negates this part, and the retained condition/limitation.",
      "evidence": [
        {
          "document_id": "doc-main-v1",
          "quote": "An exact contiguous quotation copied from this document only",
          "locator": "v1's own page/section/table, or null",
          "outcome": "supported",
          "review_note": "Per-document examined meaning, including conditions."
        }
      ]
    }
  ]
}
```

Every input claim needs exactly one reviewed decision. Every evidence item has **one** `document_id`, never a list; the script attaches that document's immutable version to the evidence. `outcome` is the agent's per-document semantic examination, not a pooled claim verdict. The script is an exact-quote and accounting validator, **not** a semantic entailment oracle.

A quotation must be a nonempty exact substring of the bound document's readable text. Do not relocate a quote from v1 to v2, from a supplement to its main text, or from an abstract to a correction. A quote absent from the bound version fails `quote_verified`; absence alone does not make the claim contradicted. Keep original conditions, hedges, denominators, and negation in the quote whenever needed for the claim.

Supplemental locators are supplement-local. Never inherit main-text page numbers, table labels, appendices, or experimental conditions. A main document failing to report a supplement-only condition does not refute that conditional claim.

### 6. Derive version-scoped verdicts and artifacts

Every claim that can receive a verdict must have a nonempty `version_scope` listing the specific document IDs to which it is limited. For a claim spanning versions, inspect and separately account for every scoped version. Rewrite vague wording into visible version-specific statements when necessary. If scope cannot be established, use `insufficient_evidence`.

Apply the full rules in [references/identity-and-versions.md](references/identity-and-versions.md), especially:

- One scoped document: use its direct valid examined evidence. For a `version_comparison` claim, fewer than two scoped versions is automatically `insufficient_evidence` because comparison is impossible.
- Multiple scoped documents: all affirmative can support; all explicitly negative can contradict; affirmative on some versions but negative/missing/partial on others is partial; all missing/unknown is insufficient.
- Opposed v1 and v2 statements remain side by side in the matrix with `partially_supported` for an unchanged-across-versions claim. Do not turn “v2 is newer” into proof or average two numerical results.
- A supplement-only conditional claim can be supported strictly within the supplement's `version_scope`; this says nothing about unconditional main-text performance.

Run:

```bash
python3 /skills/weekly-skill/scripts/reconcile.py finalize \
  --input /input \
  --work /app/work \
  --metadata /app/work/reviewed-source-metadata.json \
  --evidence /app/work/reviewed-evidence-map.json \
  --output /app/output/result.json
```

This independently regenerates:

- `/app/work/version-matrix.json`: identity/version columns and side-by-side claim statements per document.
- `/app/work/source-version-dag.json`: validated structural provenance, with no authority ranking.
- `/app/work/evidence-map-checked.json`: exact quote outcomes, bound files, per-document outcomes, and full scope limitations.
- `/app/work/provenance.svg`: UTF-8 text SVG generated from the reviewed documents and DAG.
- `/app/output/result.json`: contract-adapted final result built from current documents, claims, hashes, and reviewed evidence, not a prefabricated answer.

An unresolved/invalid quote or impossible comparison removes affirmative weight and produces uncertainty. Overall status remains `partial` when any claim is partial or insufficient. `complete` requires every claim to be supported, not merely all quotes to match.

### 7. Validate and read back

Before finishing, read `/app/work/source-inventory.json`, the DAG, checked evidence, version matrix, SVG, and final result. Confirm:

- Every contract key exists with the correct list/object shape and output claims preserve the input claim IDs.
- Every scoped evidence quote is verified in the same document/version, and its locator is local to that source.
- Duplicate copies were not counted twice and DOI/title/date unknowns remain `null`.
- Version differences remain explicit, no numeric or narrative pooling occurred, and supplement conditions are not generalized.
- `sources`, `uncertainty`, and `change_records` match what was actually done; read the final file from disk, not from an assumed in-memory object.

If `validate` or `finalize` exits `1`, do not report success. Preserve or restore early partial output, diagnose the controlled error, and rerun only after genuine source-based correction.

## Executable SYNTHETIC minimal example

`examples/minimal/` contains three distinct plain-text documents (v1, v2, and S2 supplement), one byte-identical v1 duplicate, two unverified input claims, and reviewed metadata/evidence files. All content is explicitly **SYNTHETIC**; DOI values are `null`, not fabricated. The generated example includes:

- real SHA-256 duplicate detection;
- a v1-supported/v2-corrected claim whose cross-version verdict is `partially_supported`;
- an H1-plus-10-degree claim supported only inside S2;
- an inventory, DAG, checked evidence map, generated version matrix, SVG, and partial final result.

Regenerate and test offline from the bundle root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tests/run_tests.py
```

The tests rebuild final artifacts from the input documents and mappings, then verify independent expected hashes. They also require exit `1` for both a DAG cycle and dangling target, wrong-document quote rejection without treating absence as contradiction, stale-hash rejection while preserving early partial output, and honest one-document comparison downgrade. The checked-in result and SVG are generated outputs, not input fixtures for producing themselves.
