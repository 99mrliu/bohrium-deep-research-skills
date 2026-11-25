# Claims ledger grammar

The ledger is agent-authored JSON. `schema_version` is
`claim-coverage-adjudication/v1`; `case_id` must exactly match the input. This is
a record grammar, not a JSON Schema dependency.

```json
{
  "schema_version": "claim-coverage-adjudication/v1",
  "case_id": "exact-input-id",
  "task_atoms": [
    {
      "atom_id": "atom-eq7-transcription",
      "exact_requirement": "Transcribe target formula eq7 without losing its MathML structure.",
      "output_fields": ["answers.equations.eq7"],
      "claims": [
        {
          "claim_id": "claim-eq7-transcription",
          "answer": "agent-authored structured transcription",
          "claim_type": "formula",
          "completion_status": "completed",
          "output_fields": ["answers.equations.eq7"],
          "formula_source_id": "eq7",
          "origin": "reported",
          "contradiction_group": "optional-shared-subject",
          "central": true,
          "evidence": [
            {
              "excerpt_id": "ex-0042",
              "source_file": "artifacts/source-formulas.xml",
              "locator": "MathML element; lines 80-91; id=eq7",
              "quote": "an exact short substring of that excerpt",
              "formula_source_id": "eq7",
              "relation": "supports"
            }
          ],
          "inference_prerequisites": [],
          "inference_rationale": "",
          "uncertainty": [],
          "missing_objects": []
        }
      ]
    }
  ],
  "contradictions": [],
  "missing_objects": []
}
```

## Fields and enums

- `claim_type`: `formula`, `variable`, `derivation`, `numeric`, `statement`.
- `completion_status`: `completed`, `partial`, `not_started`,
  `insufficient_evidence`, `refuted`.
- `origin`: `reported` (explicitly stated) or `inference` (agent-derived).
- `evidence[].relation`: `supports`, `refutes`, or `context`. Only valid
  `supports` records satisfy evidentiary support. Valid refutation of a central
  answer is a blocking finding.
- `central` defaults to true. Use `central: false` with
  `completion_status: refuted` to retain a rejected alternative without treating
  it as the delivered answer. Do not use this flag just to bypass an unresolved
  disagreement; the contradiction record and its supported resolution remain.

All atom and claim IDs are required and unique (claim IDs are globally unique).
`exact_requirement`, atom `output_fields`, and claim `output_fields` are
required. Nested answer paths indicate which declared top-level output field is
covered; both `answers.eq7` and `/answers/eq7` name `answers`.

## Evidence identity

`excerpt_id` is the source ID used by the normalized ledger. The evidence
`source_file` and `locator` must equal that excerpt's values. `quote` is a
case-sensitive substring of its `text`, including original whitespace and XML
characters after line-ending normalization. An altered quote, correct quote at
the wrong excerpt, or omitted excerpt ID fails. MathML evidence must repeat the
excerpt's `formula_source_id`; formula claims additionally carry it at the claim
level.

Use enough adjacent short records to support the whole answer. Multiple distinct
premises should not be replaced by one keyword match. The machine checks each
record independently; the agent/manual reviewer checks their joint entailment.

## Transparent inference

For `origin: inference`, provide both:

```json
"inference_prerequisites": [
  "The numerator and denominator identities are supported by claim-eq7-transcription.",
  "The denominator is explicitly nonzero in the stated condition."
],
"inference_rationale": "Substituting those supported identities permits cancellation only under the nonzero condition."
```

At least one verified supports quote is still required. Prerequisites can refer
to other claim IDs, but those claims should themselves be complete and supported.
The script checks presence and support mechanics; a person must check whether
the rationale is valid. Nested `inference: {prerequisites, rationale}` is also
accepted, but the flat fields above are canonical.

## Contradictions

A declared record has this form:

```json
{
  "contradiction_id": "conflict-score",
  "contradiction_group": "held-out-score",
  "claim_ids": ["claim-score-a", "claim-score-b"],
  "description": "The two completed claims give different values for the same subject.",
  "status": "resolved",
  "resolution": "The second is retained as noncentral/refuted because its condition is different.",
  "resolution_evidence": [
    {
      "excerpt_id": "ex-0091",
      "source_file": "artifacts/source.txt",
      "locator": "lines 8-10",
      "quote": "exact condition-setting quote",
      "relation": "supports"
    }
  ]
}
```

`status: unresolved` always blocks success. A resolved record without a
substantive resolution and verified supports quote also blocks. Simply marking a
conflict resolved while retaining different **completed central** answers in the
same group does not pass: retain the rejected answer as noncentral/refuted and
explain the disposition. This preserves the conflict history rather than
silently collapsing it.

## Result draft

The draft is separately agent-authored and maps exact answers to exact contract
fields. `output_contract.required_fields` is preferred; legacy `fields` as a
list, list of `{name: ...}`, or object is accepted. `field_types` supports
`string`, `object`, `array`, `boolean`, `integer`, `number`, and `null`, and
`status_enum` restricts final status. `case_id` is always required even if the
contract forgets to list it.

The finalizer outputs declared fields plus the adjudicated status. It repopulates
`evidence`, augments object-valued `uncertainty` and `artifacts`, and never
authors `answers` or any domain-specific field.
