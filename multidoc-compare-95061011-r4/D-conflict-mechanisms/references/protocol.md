# Reference protocol: scoped comparison and conflict mechanisms

## 1. Establish the unit of comparison

Read the task and every source before interpreting agreement. Define a proposition as:

`topic + comparison + metric + scope`

Scope includes claim scope (scoped/universal), material, pollutant, task, experimental conditions, applicability conditions, and limitations. Direction, where warranted, belongs to the observed result, not to the paper as a whole. Author interpretations and speculation remain separate evidence records even when adjacent to observations.

Do not create `+1/-1` claim nodes. Numeric direction is neither vote counting nor scientific relation. A negative lexical statement can complement a positive statement from another operating domain; two positive statements can be incomparable.

## 2. Normalize sources without losing citations

Text files contain paragraph markers:

```text
[paper-a-p1]
Text of the first addressable paragraph.

[paper-a-p2]
Text of the next paragraph.
```

A marker must be alone on its line and identifiers must be unique within a document. All matrix cells, evidence, and direct comparisons cite an existing `(source_document_id, paragraph_id)` pair.

For PDF inputs, the runner searches only for a locally installed `pdftotext` executable and uses `pdftotext -layout` when present. It never downloads or installs anything. Pages are separated by form feed; generated identifiers are `<source_document_id>-p<four-digit-page>-<three-digit-paragraph>`, counting non-empty blocks separated by blank lines. Use these identifiers in a production workorder. Complex PDFs require visual/manual checking: extraction order, tables, and symbols can be wrong. If no converter exists or extracted text is empty, mark the run failed and record the limitation. Never invent a citation.

## 3. Complete the common-field matrix first

The required canonical rows are `task`, `material`, `pollutant`, `metric`, `units`, and `budget`; add other decision-relevant rows such as scope. Every row has exactly one cell for every registered document, with exact source and paragraph IDs. Use `unreported` when absent and `noncomparable` when definitions preclude comparison. Never replace either with a guessed value.

Before quantitative synthesis, compare all six fields for each proposed pair, then dataset identity and applicability conditions. Mismatch, unreported values, unlike datasets, and different dyes block pooling. Qualitative interpretation may still be possible and must state the limit. A common proposition key does not override a failed compatibility check. The supplied example does no statistical aggregation or pooling; capacities are displayed only as originally reported.

## 4. Extract evidence and scope

For each proposition:

- use an agent-specified exact `proposition_key`;
- record topic, comparison, metric name and unit, material set, pollutant set, task, claim scope, applicability conditions, and limitations;
- cite one or more evidence IDs and preserve their evidence kind;
- include measurements as reported, without recalculating to force alignment;
- keep strength wording and statistical significance separate;
- omit `direction` unless an observed result directly supports it. A small numerical difference alone does not justify `no_difference`; that requires an appropriate equivalence/precision argument.

A universal author claim can be recorded as such, but its evidence and limitations must remain visible. Do not silently convert it to a demonstrated universal fact.

## 5. Cluster only explicit keys and judge explicit pairs

`cluster_propositions.py` groups by exact `proposition_key`, after checking that the key appeared in `agent_specified_proposition_keys`. It performs no fuzzy, embedding, token, alias, or inferred entity matching. Scientific comparability is a later check, not an assumption of clustering.

Judge only relation pairs explicitly supplied in `conflict_relations`:

- **corroborates**: comparable estimand and matched conditions, with supporting observed directions;
- **complements**: covered scopes or questions extend one another without contradiction;
- **genuine_conflict**: comparable estimand and matched conditions, with incompatible observed results;
- **apparent_conflict_due_to_scope**: apparent opposition is between different conditions or applicability domains;
- **incomparable**: task, metric/unit, material, pollutant/dye, or estimand cannot support the relation;
- **insufficient**: missing observations, ambiguous scope, or inadequate reporting prevents another verdict.

A genuine conflict is not automatically resolved by noticing different synthesis batches, instruments, or conditions. Such differences are candidate explanations only.

## 6. Attribute mechanisms cautiously

For each mechanism, record:

- one of `supported_by_direct_comparison`, `consistent_with_conditions`, `unresolved`;
- supporting explanations and their evidence;
- alternative explanations, including untested alternatives;
- direct comparisons, if any, with exact citations, `observed_result`, `direct_head_to_head` design, and the tested moderator.

`supported_by_direct_comparison` requires an actual within-paper head-to-head comparison that tests the proposed moderator while relevant conditions are controlled. An author saying “because,” an observed covariation across papers, or a condition difference alone cannot establish it. Direct support remains bounded to the tested system and does not eliminate every alternative.

## 7. Synthesize and report honestly

The atlas presents propositions, clusters, explicit verdicts, mechanisms, alternatives, limitations, and compatibility decisions. The integrated response is concise: state what is supported, what genuinely conflicts and remains unresolved, what merely extends scope, and what cannot be compared.

`result.json` uses the exact input `case_id`; retains the original output contract; includes status, sources, uncertainties, and change records; and dynamically adds requested contract fields. `success` means all requested artifacts/fields and validations are complete, `partial` means some are unreported or unresolved at the contract level, and `failed` means the pipeline could not produce a valid comparison. A scientific conflict remaining unresolved does **not** make the software run partial or failed.
