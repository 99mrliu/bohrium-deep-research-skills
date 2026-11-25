# Claim–evidence map (SYNTHETIC example)

- **Case:** `SYNTHETIC-NEGATIVE-NO-PROMOTION`
- **Run status:** `insufficient_evidence`
- **Reading rule:** conclusions, limitations, hypotheses, observations, and cited claims remain separate discourse layers.

## Requested fields

| field_id | status | scalar | units | statistic | condition | comparator | primary location |
|---|---|---|---|---|---|---|---|
| established_current_author_mechanism | not_reported | — | — | — | Mechanism of additive X in the current study; explicitly not tested | — | N1 |

## Discourse-layered claims

### NEG-CITED — `prior_work_cited_claim`

Zhao et al.'s cited result concerns their system; transfer of the mechanism to the current system is only suggested and remains untested here.

- Attribution: Zhao et al., as cited in the synthetic source (`cited_work`)
- Epistemic status: `cited_hedged_claim`; modality: `reported_and_speculative`
- Preserved hedges: `could`, `suggesting`, `might`, `did not test`
- Promotion allowed: `false`
- Evidence `SRC-SYN-NEG/N1`: “Zhao et al. reported that additive X could suppress the unwanted pathway in their system, suggesting that the same mechanism might operate here; we did not test that mechanism in the present study.”

## Quantitative and qualitative observations

## Conditions


## Uncertainties and non-promotion boundaries

- `non_promotion_boundary`: The cited original is unavailable and no current-study mechanistic test is reported. No affirmative scalar is licensed.
- `not_reported`: The entire synthetic source was inspected. The cited hedged proposition addresses background, not an established current-author mechanism; missing does not mean zero or false. Claim layers: NEG-CITED=prior_work_cited_claim/cited_hedged_claim.
- `epistemic_boundary`: prior_work_cited_claim; modality=reported_and_speculative; no promotion to established current-author fact

## Graph audit

Generated **5 nodes** and **2 directed edges**. `grounded_in` edges carry exact quotations; `supported_by` does not mean `proven`.
