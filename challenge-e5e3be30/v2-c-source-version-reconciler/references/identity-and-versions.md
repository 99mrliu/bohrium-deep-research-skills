# Source identity and version-scoped verdict rules

## Identity hierarchy

Keep these identities separate. Never infer a missing identifier from a similar title.

| Level | Meaning | Allowed evidence | Examples |
|---|---|---|---|
| `file` | One byte sequence at one location. | A SHA-256 digest over the actual input bytes, size, and path. | Two directories can contain identical copies with the same digest. |
| `document` | One immutable source version. A `document_id` identifies exactly one version, never a floating “latest” paper. | Agent-reviewed `source-metadata.json`; each referenced `file_id` must exist in the inventory and every file for one document must have one digest. | Preprint v1, preprint v2, publisher version, correction, and supplement are different documents. |
| `work` | A human assertion that documents belong to the same intellectual work family. | Only an explicit, supported DOI/title/relation mapping. Do not infer work identity from digest equality alone. | `v2 --revises--> v1`; `supplement --supplements--> v2`. |
| `claim evidence` | A quotation or table observation tied to one document and its locator. | Exact substring lookup in that document's readable text; the claim-based verdict constructor records the document's version. | “Model A: 80%” in v1 is not evidence that v2 says 80%. |

Unknown DOI, title, date, version, or relation is `null` or omitted as allowed by the schema. Never guess a DOI or silently replace `null` with a label inferred from a filename. Publishers' “version of record,” accepted manuscripts, repository preprints, corrections, and supplements must not be merged merely because their titles agree.

An inventory `duplicate_of` means only byte-for-byte file duplication. It does not establish authorship, work identity, chronological order, or substantive equivalence between non-identical versions.

## Relation DAG

Relations are directed to the document they describe:

- `revises`: this document revises another version.
- `corrects`: this document corrects another document.
- `supplements`: this document supplements a main document.
- `retracts`: this document retracts another document.
- `version_of`: this document identifies another document as a version anchor.
- `related_to`: an explicitly documented identity relation without a precedence claim.

Every target `document_id` must exist. Cycles and dangling targets are fatal metadata errors; the CLI exits `1` before rendering a final result. The DAG proves structural validity only, not authority, chronological truth, or factual support. A relation must have an evidence basis outside the script whenever the relationship matters.

A supplement normally points to its own main document. Its tables and page numbers are local to the supplemental file. A correction changes only what it explicitly changes; it does not silently rewrite all other claims.

## Evidence binding and quote lookup

Each evidence item binds exactly one existing `document_id`; there is no document-level array and no pooled evidence across documents. A document's version is attached by the constructor, not separately asserted in an evidence item. Every referenced file must have matching content hashes. Non-text or text-extraction-failed documents can be inventoried but cannot support a quote; record that uncertainty or provide a separate verified-text extraction with provenance.

Quotes are exact, nonempty Unicode substring matches in the bound document's combined readable files. For duplicate copies of the same digest, one exact match is enough. A quote matching another document but not the bound document fails. `../`, absolute paths, and references outside the input tree are rejected. No automatic page inheritance is performed.

## Four-level claim verdicts

The claim-status constructor is a manually reviewed decision gate, not a semantic text-entailment oracle.

- `supported`: Valid, directly bound evidence supports the claim *within its declared version scope*. If the claim crosses documents, every document in `version_scope` must have affirmative evidence (`documents_supported`), and there must be no required document with an unresolved conflict.
- `partially_supported`: Only part of the requested claim or only some documents in `version_scope` have affirmative evidence; alternatively a within-version mixed statement meets this level. Use it for a single claim that is true for v1 but revised for v2. Do not average the versions into one pooled conclusion.
- `contradicted`: Valid evidence explicitly negates the requested claim in all applicable parts, or evidence across `version_scope` contradicts it with no affirmative qualifying support. Silence, a missing quotation, or an unreported result is **not** contradiction.
- `insufficient_evidence`: No valid direct evidence, failed quote checks, unknown scope, unreadable documents, an empty comparison, or evidence that is merely topic-related. A document can disagree without proving that a missing condition is false.

`documents_supported`, `documents_partial`, `documents_contradicted`, `documents_insufficient`, and `documents_missing` make the per-document inspection auditable. When more than one version is addressed, a claim with both affirmative and negative per-document outcomes must not be collapsed to `supported` or `contradicted`; use `partially_supported` and show the divergent version statements together.

For a single document, downgrade honestly: report that cross-version comparison is impossible. This does not create another version, manufacture a conflict, or prevent a supported claim strictly scoped to that one document when its wording is only about that document.

## Version-scope contract

Every claim reaching a verdict has a nonempty `version_scope`: the specific `document_id` values to which the verdict is limited. A claim about “the current model” must first be rewritten as separately visible v1 and v2 statements, or be marked unresolved. An unscoped synthesis that would cross versions cannot inherit the v2 date, DOI, pagination, or evidence from v1.

Version differences are parallel assertions, not a tournament. Newer does not automatically mean true. A correction can be pertinent without establishing global supremacy. Preserve differing quotations, outcomes, and limitations per version in the version matrix. Do not pool numerators, denominators, quotations, or conclusions across preprints, revised versions, versions of record, corrections, or supplements.

A supplement-only claim must name the supplement document in `version_scope`, with `condition` and `supplement_only` made explicit. Its supporting quotation must exist in the supplemental text. Do not attribute supplemental page numbers, appendices, conditions, or performance values to the main document.
