# Discourse and evidence rules

## 1. The unit of analysis is a situated proposition

For each proposition, ask five separate questions before assigning a target value:

1. **Who asserts it?** Current authors, current data, or a cited third party?
2. **What speech act is it?** Method/report, conclusion, limitation, hypothesis/speculation, or cited background?
3. **How certain is the wording?** Declarative, possible, speculative, conditional, or bounded? Preserve the operative phrase literally.
4. **What observations are offered as support?** Link those observations, but do not confuse support with proof.
5. **Where and under what conditions does it hold?** Population/material/sample, run, setting, time, comparator, source paragraph/page/table scope.

A sentence can contain several units. Split “A increased, suggesting B, consistent with C et al.” into a current observation, a speculative mechanistic claim, and a cited alignment statement. Do not give the entire sentence the strongest discourse class found anywhere in it.

## 2. Kind decision table

| Kind | Evidence needed | Attribution and epistemic treatment | Typical trap |
|---|---|---|---|
| `author_conclusion` | Current authors explicitly interpret/conclude from current work | `origin: author_current_paper`; `epistemic_status: author_conclusion` or `concluded_by_authors`; declarative modality | Turning “suggests” or a cited statement into a current conclusion |
| `limitation` | Restricted scope, unknown, untested dimension, caveat, or qualification | Current/cited origin must be explicit; `promotion_allowed: false` | Dropping “only,” duration, population, or unknown scope |
| `hypothesis_speculation` | Proposal, possibility, interpretation offered without direct establishment, future work | Usually current authors; non-declarative modality and `promotion_allowed: false` | Replacing may/might/could with “is,” “causes,” or “demonstrates” |
| `method_observation` | Procedure, measurement, direct qualitative or quantitative report | Keep method and observation distinct from downstream interpretation | Treating a measured endpoint as proof of mechanism |
| `prior_work_cited_claim` | A report/proposition explicitly attributed to another work | `origin: cited_work`, named speaker as available, `promotion_allowed: false` | Promoting cited value to current-paper result or stripping as-cited status |

A directly stated current conclusion may contain appropriate conditions (“under these conditions”); those conditions are mandatory. A conclusion can coexist with a limitation or speculation in the same paragraph. Graph nodes remain separate.

## 3. Non-promotion invariants

- Cited + hedged never entails established current-author fact.
- Current + speculative never entails established current-author fact.
- Observed association never entails a proposed mechanism.
- A field status of `reported` can mean “the hypothesis is reported as a hypothesis.” It does **not** mean its proposition is established.
- A claim used to answer a requested “established conclusion” cannot supply a positive value when the actual source is only cited or speculative. Return `not_reported`, null scalar, and exact non-promotion evidence.
- `supported_by` is a directed discourse relation from claim to observation. There is no graph traversal that changes claim kind.

The builder additionally requires a field `interpretation` annotation when a target links to guarded claims:

- `reported_hypothesis`
- `reported_prior_work`
- `reported_limitation`
- `not_an_established_author_conclusion` when the target is `not_reported`

This annotation is consumed during validation and represented in the output notes and graph; it is not a license to paraphrase away the original hedges.

## 4. Hedges, modality, and attribution

Record each meaningful hedge exactly as written in `hedges`. It must occur in the claim text or evidence. Include scope markers that operators often erase: “in this system,” “under the tested conditions,” “up to,” “within 6 h,” “in our hands,” “preliminary,” “not directly measured,” “independently of.”

Examples of safe and unsafe reading:

- Source: “The higher rate **may reflect** faster transport.”  
  Safe scalar: “Untested author hypothesis: faster transport may explain the higher rate.”  
  Unsafe: “Faster transport causes the higher rate.”
- Source: “Lee et al. **showed** X at 50 °C.”  
  Safe kind: `prior_work_cited_claim`, even though “showed” is declarative in the cited work. The current authors' certainty and original cited claim are different layers.
- Source: “I conclude A outperforms B **for this substrate under batch conditions**.”  
  Safe kind: `author_conclusion` with the substrate/batch condition attached.  
  Unsafe: “A is universally better.”

Do not infer citation completeness. If only “Lee et al.” is present, citation metadata beyond that is unknown.

## 5. Observations, conditions, comparators, and statistics

Create one observation per entity/run/value unless the task explicitly requests a stated aggregate. Never create a synthetic average by averaging paper groups. Record a range/list exactly when it cannot be faithfully represented as one scalar; use a string scalar with a note instead of inventing a distribution.

Condition linkage can require several evidence spans:

- Methods paragraph: sample and instrument;
- Results paragraph: shorthand “under these conditions”;
- Table title/footnote: duration and error definition;
- Caption/supplement: comparator identity or replicate count.

The condition description is curated text, but every component must have source support. Link observation to its condition IDs; the builder joins condition descriptions and rejects a field-level override that differs from them. Keep an absent experimental detail explicit as “not reported in inspected source,” not an invented standard condition.

`statistic` should retain replicate type/count, mean/median, SD/SEM/CI, p value, or “single value/statistic not reported” as supported. Do not convert SD into SEM, a range into SD, or percentages into fractions. `comparator` identifies the precise baseline/control and its conditions; a cited result is not automatically a valid like-for-like comparator.

## 6. Absence, failures, and conflicts

- `not_reported`: the defined material and target scope were inspected; cite the closest explicit limitation/availability statement where possible, and state the searched sections/tables in notes. If only part of the paper was inspected, usually use `extraction_failed` instead.
- `extraction_failed`: likely-relevant source could not be read reliably (image table, failed PDF extraction, malformed rows, unresolved cross-reference). Name the missing artifact/page/paragraph and manual action.
- `source_conflict`: two or more incompatible values for the same requested entity/condition/statistic remain after checking scope. Link at least two observations and two locations. Null scalar, expose both in observations/graph/notes. Different conditions may explain a difference; then they may be distinct reported observations rather than a conflict, if the target permits scope separation.

Neither absence nor conflict is zero.

## 7. Review pass

Before finalizing, make a proposition-by-proposition pass:

1. Cover every target and every source section permitted by the task.
2. Read claim evidence aloud with its attribution; check whether the output adds a stronger speech act.
3. Trace each numeric field through observation → condition → evidence edges.
4. Trace each author conclusion to observations and limitations.
5. Check abstract wording against results/discussion; abstract compression is not permission to erase caveats.
6. Ensure the Markdown map remains readable and displays the same layers as JSON.
