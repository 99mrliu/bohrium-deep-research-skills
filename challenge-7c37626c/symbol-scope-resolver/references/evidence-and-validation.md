# Evidence categories, quantity provenance, and failure gates

| Category | Meaning | Required evidence and restrictions |
|---|---|---|
| `direct_source_definition` | The paper directly defines this scoped meaning. | Same-scope definition `selected_candidate_id`; evidence quote and locator exactly equal that candidate; quote is a literal source substring. |
| `contextual_inference` | The analysis infers meaning from context rather than a defining statement. | Non-empty `inference_reason`; any optional source quote must pass the same exact-substring/scope check. Do not present it as the paper's explicit definition. |
| `common_knowledge_external` | Meaning comes from outside the article. | Non-empty `external_basis`, `attribution: external_not_paper`, and no selected paper candidate/evidence object. Never say the paper supplied it. |
| `not_reported` | The source does not supply a grounded meaning. | Non-empty `reason`; keep unknown values null. |
| `conflict` | At least two incompatible candidate claims survive. | At least two retained claims, each with its candidate ID, exact quote, locator, and claim text. Do not write over the conflict with a preferred global definition. |

A definition's category does not automatically prove its unit or range. Units and
ranges carry separate provenance using the same categories except `conflict`:

- Literal (`direct_source_definition`) quantities require `evidence_quote` and a
  same-scope source locator. A definition candidate alone is insufficient if the
  sentence does not literally contain the quantity/unit.
- Inferred quantities require `inference_reason`; external quantities require
  `external_basis` and `attribution: external_not_paper`.
- `not_reported` means value/lower/upper/text is null. It cannot carry a value.
- Null is not zero. This distinction is mandatory for C02 and every other source
  lacking values.

## Validator outcomes

`finalize.py --validate-only` prints a report and exits 0 when valid or 2 when
invalid. Fatal input/JSON failures exit 1. Normal finalization emits tables and
result even on validation errors, retains partial/invalid status, prints a
non-silent diagnostic, and exits 2.

Hard failures include fabricated/non-substring evidence, unselected direct
candidates, evidence from another scope, discarded full scripts, duplicate or
missing formula coverage, covered formulae omitting any scoped symbol ID,
unreasoned inference/external claims, unsupported quantities, and malformed
conflicts. Unbound symbols are warnings that prevent complete status.

The final status is dynamic: no formula representation prefers
`insufficient_evidence`, then `partial`; incomplete or invalid analysis prefers
`partial` when available. A complete status requires no validation errors, no
unbound symbols, and no incomplete formula coverage. Contract field names come
from `required_fields`, `field_types`, and typed properties. Unknown numeric or
boolean fields stay null and generate a warning rather than being zero/false
filled. Agent values for case-specific fields belong in `output_fields`.

## Human review after validation

Validation proves structural and quotation consistency, not semantic truth.
Inspect the actual paragraph around each direct definition, check anaphora such
as “these quantities,” and ensure the agent's meaning does not exceed the quote.
Review each inferred/external quantity and every exclusion reason. Confirm that
`variable_table.md`, `variable_table.json`, and `result.json` retain all conflicts,
limitations, and scoped symbols before delivery.
