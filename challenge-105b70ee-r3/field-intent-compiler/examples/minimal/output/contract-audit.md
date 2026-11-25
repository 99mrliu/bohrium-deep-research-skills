# SYNTHETIC Field Acceptance Contract and Audit

**SYNTHETIC EXAMPLE — NOT A FORMAL TEST RESULT.**

- case_id: `SYNTHETIC-FIELD-INTENT-001`
- overall status: `partial`
- contract SHA-256: `37cb8680bc58438b9f359bf742193382d03b8b45d12ecfa661f1ed2d08ca3acf`
- compilation order: QUESTION/SCHEMA and tests precede source paragraph adjudication.
- quote policy: exact quotation is necessary evidence integrity, never sufficient semantic proof.
- selection policy: all values and semantic check rationales are agent-authored; the compiler does not keyword-rank candidates.

## Pre-candidate acceptance contracts

### `F_YIELD_120C`

- field kind: `value`
- metric_identity: `product yield`
- subject_entity: `SYNTHETIC Catalyst X`
- expected_value_form: `single numeric scalar`
- requested_unit: `%`
- statistic: `single reported value`
- required_condition: `temperature=120 °C AND solvent=toluene`
- comparator: `none`
- source_scope: `["S_SYNTHETIC"]`
- modality: `not_applicable`

Tests compiled before candidates:

- `F_YIELD_120C::metric_identity` (agent_semantic_adjudication): The candidate is the requested metric, not a same-named or co-located different metric.
- `F_YIELD_120C::subject_entity` (agent_semantic_adjudication): The candidate describes the requested subject/entity, not another arm, material, group, or time point.
- `F_YIELD_120C::expected_value_form` (agent_semantic_adjudication): The candidate has the requested value form (for example scalar, range, text, or list) without silent reshaping.
- `F_YIELD_120C::requested_unit` (agent_semantic_adjudication): The candidate preserves the requested unit; any conversion is explicitly requested and separately auditable.
- `F_YIELD_120C::statistic` (agent_semantic_adjudication): The candidate is the requested statistic, not a raw observation, mean, SD, SE, CI, or other statistic substituted for it.
- `F_YIELD_120C::required_condition` (agent_semantic_adjudication): All required conditions are satisfied together by the same candidate evidence; a same value under another condition is rejected.
- `F_YIELD_120C::comparator` (agent_semantic_adjudication): The comparator/baseline/direction is the requested one, including an explicit no-comparator interpretation when applicable.
- `F_YIELD_120C::source_scope` (agent_semantic_adjudication): The candidate and search are inside the permitted source scope; out-of-scope text cannot establish the answer.
- `F_YIELD_120C::modality` (agent_semantic_adjudication): For a conclusion field, author conclusion, speculation, limitation, and reported fact are distinguished from the wording; otherwise modality is not applicable.
- `F_YIELD_120C::verbatim_evidence` (compiler_plus_agent): The exact quote is present in the identified paragraph and contains the verbatim value. This is necessary but never sufficient for acceptance.

### `F_YIELD_SD_120C`

- field kind: `value`
- metric_identity: `product yield variability`
- subject_entity: `SYNTHETIC Catalyst X`
- expected_value_form: `single numeric scalar`
- requested_unit: `percentage points`
- statistic: `standard deviation`
- required_condition: `temperature=120 °C AND solvent=toluene`
- comparator: `none`
- source_scope: `["S_SYNTHETIC"]`
- modality: `not_applicable`

Tests compiled before candidates:

- `F_YIELD_SD_120C::metric_identity` (agent_semantic_adjudication): The candidate is the requested metric, not a same-named or co-located different metric.
- `F_YIELD_SD_120C::subject_entity` (agent_semantic_adjudication): The candidate describes the requested subject/entity, not another arm, material, group, or time point.
- `F_YIELD_SD_120C::expected_value_form` (agent_semantic_adjudication): The candidate has the requested value form (for example scalar, range, text, or list) without silent reshaping.
- `F_YIELD_SD_120C::requested_unit` (agent_semantic_adjudication): The candidate preserves the requested unit; any conversion is explicitly requested and separately auditable.
- `F_YIELD_SD_120C::statistic` (agent_semantic_adjudication): The candidate is the requested statistic, not a raw observation, mean, SD, SE, CI, or other statistic substituted for it.
- `F_YIELD_SD_120C::required_condition` (agent_semantic_adjudication): All required conditions are satisfied together by the same candidate evidence; a same value under another condition is rejected.
- `F_YIELD_SD_120C::comparator` (agent_semantic_adjudication): The comparator/baseline/direction is the requested one, including an explicit no-comparator interpretation when applicable.
- `F_YIELD_SD_120C::source_scope` (agent_semantic_adjudication): The candidate and search are inside the permitted source scope; out-of-scope text cannot establish the answer.
- `F_YIELD_SD_120C::modality` (agent_semantic_adjudication): For a conclusion field, author conclusion, speculation, limitation, and reported fact are distinguished from the wording; otherwise modality is not applicable.
- `F_YIELD_SD_120C::verbatim_evidence` (compiler_plus_agent): The exact quote is present in the identified paragraph and contains the verbatim value. This is necessary but never sufficient for acceptance.

### `F_SELECTIVITY_120C`

- field kind: `value`
- metric_identity: `product selectivity`
- subject_entity: `SYNTHETIC Catalyst X`
- expected_value_form: `single numeric scalar`
- requested_unit: `%`
- statistic: `single reported value`
- required_condition: `temperature=120 °C AND solvent=toluene`
- comparator: `none`
- source_scope: `["S_SYNTHETIC"]`
- modality: `not_applicable`

Tests compiled before candidates:

- `F_SELECTIVITY_120C::metric_identity` (agent_semantic_adjudication): The candidate is the requested metric, not a same-named or co-located different metric.
- `F_SELECTIVITY_120C::subject_entity` (agent_semantic_adjudication): The candidate describes the requested subject/entity, not another arm, material, group, or time point.
- `F_SELECTIVITY_120C::expected_value_form` (agent_semantic_adjudication): The candidate has the requested value form (for example scalar, range, text, or list) without silent reshaping.
- `F_SELECTIVITY_120C::requested_unit` (agent_semantic_adjudication): The candidate preserves the requested unit; any conversion is explicitly requested and separately auditable.
- `F_SELECTIVITY_120C::statistic` (agent_semantic_adjudication): The candidate is the requested statistic, not a raw observation, mean, SD, SE, CI, or other statistic substituted for it.
- `F_SELECTIVITY_120C::required_condition` (agent_semantic_adjudication): All required conditions are satisfied together by the same candidate evidence; a same value under another condition is rejected.
- `F_SELECTIVITY_120C::comparator` (agent_semantic_adjudication): The comparator/baseline/direction is the requested one, including an explicit no-comparator interpretation when applicable.
- `F_SELECTIVITY_120C::source_scope` (agent_semantic_adjudication): The candidate and search are inside the permitted source scope; out-of-scope text cannot establish the answer.
- `F_SELECTIVITY_120C::modality` (agent_semantic_adjudication): For a conclusion field, author conclusion, speculation, limitation, and reported fact are distinguished from the wording; otherwise modality is not applicable.
- `F_SELECTIVITY_120C::verbatim_evidence` (compiler_plus_agent): The exact quote is present in the identified paragraph and contains the verbatim value. This is necessary but never sufficient for acceptance.

### `F_CONVERSION_120C`

- field kind: `value`
- metric_identity: `reactant conversion`
- subject_entity: `SYNTHETIC Catalyst X`
- expected_value_form: `single numeric scalar`
- requested_unit: `%`
- statistic: `single reported value`
- required_condition: `temperature=120 °C AND solvent=toluene`
- comparator: `none`
- source_scope: `["S_SYNTHETIC"]`
- modality: `not_applicable`

Tests compiled before candidates:

- `F_CONVERSION_120C::metric_identity` (agent_semantic_adjudication): The candidate is the requested metric, not a same-named or co-located different metric.
- `F_CONVERSION_120C::subject_entity` (agent_semantic_adjudication): The candidate describes the requested subject/entity, not another arm, material, group, or time point.
- `F_CONVERSION_120C::expected_value_form` (agent_semantic_adjudication): The candidate has the requested value form (for example scalar, range, text, or list) without silent reshaping.
- `F_CONVERSION_120C::requested_unit` (agent_semantic_adjudication): The candidate preserves the requested unit; any conversion is explicitly requested and separately auditable.
- `F_CONVERSION_120C::statistic` (agent_semantic_adjudication): The candidate is the requested statistic, not a raw observation, mean, SD, SE, CI, or other statistic substituted for it.
- `F_CONVERSION_120C::required_condition` (agent_semantic_adjudication): All required conditions are satisfied together by the same candidate evidence; a same value under another condition is rejected.
- `F_CONVERSION_120C::comparator` (agent_semantic_adjudication): The comparator/baseline/direction is the requested one, including an explicit no-comparator interpretation when applicable.
- `F_CONVERSION_120C::source_scope` (agent_semantic_adjudication): The candidate and search are inside the permitted source scope; out-of-scope text cannot establish the answer.
- `F_CONVERSION_120C::modality` (agent_semantic_adjudication): For a conclusion field, author conclusion, speculation, limitation, and reported fact are distinguished from the wording; otherwise modality is not applicable.
- `F_CONVERSION_120C::verbatim_evidence` (compiler_plus_agent): The exact quote is present in the identified paragraph and contains the verbatim value. This is necessary but never sufficient for acceptance.

### `F_AUTHOR_OUTLOOK`

- field kind: `conclusion`
- metric_identity: `author outlook on catalyst promise`
- subject_entity: `SYNTHETIC Catalyst X`
- expected_value_form: `verbatim conclusion sentence`
- requested_unit: `not_applicable`
- statistic: `not_applicable`
- required_condition: `under the tested conditions; preserve hedging`
- comparator: `none`
- source_scope: `["S_SYNTHETIC"]`
- modality: `author_speculation`

Tests compiled before candidates:

- `F_AUTHOR_OUTLOOK::metric_identity` (agent_semantic_adjudication): The candidate is the requested metric, not a same-named or co-located different metric.
- `F_AUTHOR_OUTLOOK::subject_entity` (agent_semantic_adjudication): The candidate describes the requested subject/entity, not another arm, material, group, or time point.
- `F_AUTHOR_OUTLOOK::expected_value_form` (agent_semantic_adjudication): The candidate has the requested value form (for example scalar, range, text, or list) without silent reshaping.
- `F_AUTHOR_OUTLOOK::requested_unit` (agent_semantic_adjudication): The candidate preserves the requested unit; any conversion is explicitly requested and separately auditable.
- `F_AUTHOR_OUTLOOK::statistic` (agent_semantic_adjudication): The candidate is the requested statistic, not a raw observation, mean, SD, SE, CI, or other statistic substituted for it.
- `F_AUTHOR_OUTLOOK::required_condition` (agent_semantic_adjudication): All required conditions are satisfied together by the same candidate evidence; a same value under another condition is rejected.
- `F_AUTHOR_OUTLOOK::comparator` (agent_semantic_adjudication): The comparator/baseline/direction is the requested one, including an explicit no-comparator interpretation when applicable.
- `F_AUTHOR_OUTLOOK::source_scope` (agent_semantic_adjudication): The candidate and search are inside the permitted source scope; out-of-scope text cannot establish the answer.
- `F_AUTHOR_OUTLOOK::modality` (agent_semantic_adjudication): For a conclusion field, author conclusion, speculation, limitation, and reported fact are distinguished from the wording; otherwise modality is not applicable.
- `F_AUTHOR_OUTLOOK::verbatim_evidence` (compiler_plus_agent): The exact quote is present in the identified paragraph and contains the verbatim value. This is necessary but never sufficient for acceptance.

## Field adjudication audit

### `F_YIELD_120C` — `reported`

- scalar: `72`; verbatim: `72`
- units: `%`; statistic: `single reported value`
- condition: `temperature=120 °C AND solvent=toluene`; comparator: `null`
- modality: `not_applicable`
- notes: SYNTHETIC: the decoy has the same literal value but fails the condition test; scalar 72 retains spelling '72' in verbatim_value.
- PASS `F_YIELD_120C::comparator`: This is an unpaired yield and the schema requests no comparator.
- PASS `F_YIELD_120C::expected_value_form`: The sentence supplies one numeric value rather than a range.
- PASS `F_YIELD_120C::metric_identity`: The sentence explicitly names product yield, not conversion or selectivity.
- PASS `F_YIELD_120C::modality`: This numeric field is not a conclusion field.
- PASS `F_YIELD_120C::requested_unit`: The percent sign directly follows 72; no conversion was made.
- PASS `F_YIELD_120C::required_condition`: 120 °C and toluene jointly bind the 72% yield in this sentence.
- PASS `F_YIELD_120C::source_scope`: The evidence is in the sole permitted source S_SYNTHETIC.
- PASS `F_YIELD_120C::statistic`: The selected sentence reports one value and no variability statistic.
- PASS `F_YIELD_120C::subject_entity`: The yield is predicated of Catalyst X.
- PASS `F_YIELD_120C::verbatim_evidence`: The quote is exact and contains the verbatim token 72; semantic checks above are separately satisfied.
- REJECTED `72` via `F_YIELD_120C::required_condition`: Rejected despite the identical number and unit: this occurrence is at 80 °C, not the required 120 °C.
- EVIDENCE `S_SYNTHETIC/p-yield-120C` page `1`: “At 120 °C in toluene, Catalyst X gave a yield of 72%.”

### `F_YIELD_SD_120C` — `not_reported`

- scalar: `null`; verbatim: `null`
- units: `null`; statistic: `null`
- condition: `null`; comparator: `null`
- modality: `null`
- notes: SYNTHETIC: three replicates are mentioned, but a replicate count is not a standard deviation and no SD value was invented.
- SEARCH RECORD: `[{"page": 1, "paragraph_id": "p-decoy-80C", "source_id": "S_SYNTHETIC"}, {"page": 1, "paragraph_id": "p-yield-120C", "source_id": "S_SYNTHETIC"}, {"page": 1, "paragraph_id": "p-replicates", "source_id": "S_SYNTHETIC"}, {"page": 2, "paragraph_id": "p-selectivity-a", "source_id": "S_SYNTHETIC"}, {"page": 2, "paragraph_id": "p-selectivity-b", "source_id": "S_SYNTHETIC"}, {"page": 3, "paragraph_id": "p-conversion-unreadable", "source_id": "S_SYNTHETIC"}, {"page": 3, "paragraph_id": "p-outlook", "source_id": "S_SYNTHETIC"}]`; All seven paragraphs in the allowed synthetic source were searched; the yield sentence and replicate statement do not report an SD, and the other paragraphs concern other fields.

### `F_SELECTIVITY_120C` — `source_conflict`

- scalar: `null`; verbatim: `null`
- units: `null`; statistic: `null`
- condition: `null`; comparator: `null`
- modality: `not_applicable`
- notes: SYNTHETIC: both 90% and 88% satisfy the field semantics but disagree; no source-priority rule was invented and no scalar was selected.
- PASS `F_SELECTIVITY_120C::comparator`: Neither value is a comparative effect and no comparator was requested.
- PASS `F_SELECTIVITY_120C::expected_value_form`: Each candidate is a single numeric scalar; the field-level answer remains unresolved because they disagree.
- PASS `F_SELECTIVITY_120C::metric_identity`: Both candidates explicitly report selectivity, the requested metric.
- PASS `F_SELECTIVITY_120C::modality`: This numeric field is not a conclusion field.
- PASS `F_SELECTIVITY_120C::requested_unit`: Both values carry an explicit percent unit.
- PASS `F_SELECTIVITY_120C::required_condition`: Both values are jointly bound to 120 °C and toluene.
- PASS `F_SELECTIVITY_120C::source_scope`: Both paragraphs belong to the permitted source.
- PASS `F_SELECTIVITY_120C::statistic`: Each statement presents a single value, not an error estimate.
- PASS `F_SELECTIVITY_120C::subject_entity`: Both statements predicate selectivity of Catalyst X.
- PASS `F_SELECTIVITY_120C::verbatim_evidence`: Each value is contained in its own exact quote; matching alone was not used to choose between them.
- CONFLICT CANDIDATE `90` at `S_SYNTHETIC/p-selectivity-a` page `2`
- CONFLICT CANDIDATE `88` at `S_SYNTHETIC/p-selectivity-b` page `2`
- EVIDENCE `S_SYNTHETIC/p-selectivity-a` page `2`: “At 120 °C in toluene, Catalyst X showed 90% selectivity in the main-text table.”
- EVIDENCE `S_SYNTHETIC/p-selectivity-b` page `2`: “At 120 °C in toluene, Catalyst X showed 88% selectivity in the supplementary rerun.”

### `F_CONVERSION_120C` — `extraction_failed`

- scalar: `null`; verbatim: `null`
- units: `null`; statistic: `null`
- condition: `null`; comparator: `null`
- modality: `null`
- notes: This is an access/readability failure, not a claim that conversion was unreported and not a zero value.
- EVIDENCE `S_SYNTHETIC/p-conversion-unreadable` page `3`: “At 120 °C in toluene, Catalyst X conversion table cell: [illegible].”
- FAILURE: SYNTHETIC: the relevant conversion table cell is present only as '[illegible]' in the supplied source register, so the reported scalar cannot be recovered.

### `F_AUTHOR_OUTLOOK` — `reported`

- scalar: `These results suggest that Catalyst X may be promising under the tested conditions.`; verbatim: `These results suggest that Catalyst X may be promising under the tested conditions.`
- units: `null`; statistic: `null`
- condition: `under the tested conditions; preserve hedging`; comparator: `null`
- modality: `author_speculation`
- notes: SYNTHETIC: hedging is preserved; no upgrade to a definitive author conclusion.
- PASS `F_AUTHOR_OUTLOOK::comparator`: The outlook has no comparator and none is requested.
- PASS `F_AUTHOR_OUTLOOK::expected_value_form`: The complete conclusion sentence is retained verbatim.
- PASS `F_AUTHOR_OUTLOOK::metric_identity`: The sentence states the author's outlook about catalyst promise.
- PASS `F_AUTHOR_OUTLOOK::modality`: 'suggest' and 'may' are preserved and classified as author_speculation, not an established conclusion.
- PASS `F_AUTHOR_OUTLOOK::requested_unit`: No unit is applicable to this textual conclusion.
- PASS `F_AUTHOR_OUTLOOK::required_condition`: The qualification 'under the tested conditions' remains attached to the statement.
- PASS `F_AUTHOR_OUTLOOK::source_scope`: The conclusion comes from the permitted synthetic source.
- PASS `F_AUTHOR_OUTLOOK::statistic`: No statistic is applicable or inserted.
- PASS `F_AUTHOR_OUTLOOK::subject_entity`: The outlook explicitly concerns Catalyst X.
- PASS `F_AUTHOR_OUTLOOK::verbatim_evidence`: The entire sentence is an exact paragraph substring and is also the scalar.
- EVIDENCE `S_SYNTHETIC/p-outlook` page `3`: “These results suggest that Catalyst X may be promising under the tested conditions.”

## Uncertainties

- `F_YIELD_SD_120C` `not_reported`: SYNTHETIC: three replicates are mentioned, but a replicate count is not a standard deviation and no SD value was invented.
- `F_SELECTIVITY_120C` `source_conflict`: SYNTHETIC: both 90% and 88% satisfy the field semantics but disagree; no source-priority rule was invented and no scalar was selected.
- `F_CONVERSION_120C` `extraction_failed`: SYNTHETIC: the relevant conversion table cell is present only as '[illegible]' in the supplied source register, so the reported scalar cannot be recovered.

## Registered sources used for validation

- `S_SYNTHETIC`: SYNTHETIC Catalyst X excerpt (invented; not a publication)
