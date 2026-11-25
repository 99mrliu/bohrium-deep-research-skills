# Claim–evidence map (SYNTHETIC example)

- **Case:** `SYNTHETIC-MINIMAL-NOT-A-TEST-CASE`
- **Run status:** `answered`
- **Reading rule:** conclusions, limitations, hypotheses, observations, and cited claims remain separate discourse layers.

## Requested fields

| field_id | status | scalar | units | statistic | condition | comparator | primary location |
|---|---|---|---|---|---|---|---|
| catalyst_A_yield | reported | 82 | % yield | mean of three independent runs; standard deviation = 2 percentage points | 20 mg catalyst, 1.0 mmol substrate, 5 mL water, 80 °C for 6 h under 1 atm N2; yield measured by calibrated GC using an internal standard | catalyst B: 61% yield; mean of three independent runs; standard deviation = 3 percentage points; paired run under COND-REACTION | P2 |
| desorption_mechanism | reported | Untested author hypothesis: faster intermediate desorption may explain the higher yield. | — | — | Prompted by the catalyst A/B comparison under COND-REACTION; the mechanism itself was not tested | No alternative mechanism was tested or reported | P5 |
| stability_beyond_6h | not_reported | — | — | — | Catalyst A stability beyond 6 h under COND-REACTION | — | P4 |
| cited_related_catalyst_yield | reported | 90 | % yield | — | Cited related catalyst at 100 °C; other experimental conditions not reported in the current excerpt | Not a controlled comparison with catalyst A: this is cited work at 100 °C, with other conditions unreported here. | P6 |

## Discourse-layered claims

### CL-CONC — `author_conclusion`

The current authors conclude that catalyst A is more active than catalyst B only under the tested conditions.

- Attribution: current synthetic-paper authors (`author_current_paper`)
- Epistemic status: `author_conclusion`; modality: `declarative`
- Preserved hedges: none
- Promotion allowed: `true`
- Evidence `SRC-SYN-MIN/P3`: “These observations lead us to conclude that catalyst A is more active than catalyst B under the tested conditions.”

### CL-LIM — `limitation`

Only one substrate was tested; stability beyond 6 h, broader generality, and long-term durability remain unknown.

- Attribution: current synthetic-paper authors (`author_current_paper`)
- Epistemic status: `declared_limitation`; modality: `declarative`
- Preserved hedges: none
- Promotion allowed: `false`
- Evidence `SRC-SYN-MIN/P4`: “We tested only one substrate and did not measure stability beyond 6 h; therefore, broader substrate generality and long-term durability remain unknown.”

### CL-HYP — `hypothesis_speculation`

The authors speculate that faster intermediate desorption may explain the higher yield; the mechanism was not tested.

- Attribution: current synthetic-paper authors (`author_current_paper`)
- Epistemic status: `untested_hypothesis`; modality: `speculative`
- Preserved hedges: `speculate`, `may`, `not tested`
- Promotion allowed: `false`
- Evidence `SRC-SYN-MIN/P5`: “We speculate that the higher yield may arise from faster intermediate desorption, but this mechanism was not tested.”

### CL-METHOD — `method_observation`

The current-paper method used calibrated GC with an internal standard to measure yield.

- Attribution: current synthetic-paper authors (`author_current_paper`)
- Epistemic status: `directly_reported_method`; modality: `declarative`
- Preserved hedges: none
- Promotion allowed: `false`
- Evidence `SRC-SYN-MIN/P1`: “Product yield was measured by calibrated GC using an internal standard.”

### CL-PRIOR — `prior_work_cited_claim`

Chen et al., as cited here, reported up to 90% yield for a related catalyst at 100 °C and suggested higher temperature might help.

- Attribution: Chen et al., as cited in the synthetic source (`cited_work`)
- Epistemic status: `cited_hedged_claim`; modality: `reported_and_speculative`
- Preserved hedges: `could`, `suggesting`, `might`
- Promotion allowed: `false`
- Evidence `SRC-SYN-MIN/P6`: “Chen et al. reported that a related catalyst could reach 90% yield at 100 °C, suggesting that higher temperature might improve performance.”

## Quantitative and qualitative observations

### OBS-A — `quantitative_observation`

- Scalar: `82`; units: `% yield`
- Statistic: mean of three independent runs; standard deviation = 2 percentage points
- Comparator: catalyst B: 61% yield; mean of three independent runs; standard deviation = 3 percentage points; paired run under COND-REACTION
- Conditions: COND-REACTION
- Evidence `SRC-SYN-MIN/P2`: “Under these conditions, catalyst A gave 82% yield, whereas catalyst B gave 61% yield in a paired run; each value is the mean of three independent runs, and the standard deviations were 2 and 3 percentage points, respectively.”

### OBS-B — `quantitative_observation`

- Scalar: `61`; units: `% yield`
- Statistic: mean of three independent runs; standard deviation = 3 percentage points
- Comparator: catalyst A: 82% yield; mean of three independent runs; standard deviation = 2 percentage points; paired run under COND-REACTION
- Conditions: COND-REACTION
- Evidence `SRC-SYN-MIN/P2`: “catalyst B gave 61% yield in a paired run; each value is the mean of three independent runs, and the standard deviations were 2 and 3 percentage points, respectively.”

### OBS-PRIOR — `quantitative_observation`

- Scalar: `90`; units: `% yield`
- Statistic: —
- Comparator: Not a controlled comparison with catalyst A: this is cited work at 100 °C, with other conditions unreported here.
- Conditions: COND-PRIOR
- Evidence `SRC-SYN-MIN/P6`: “Chen et al. reported that a related catalyst could reach 90% yield at 100 °C”

### OBS-METHOD — `method_observation`

- Scalar: `—`; units: `—`
- Statistic: —
- Comparator: —
- Conditions: COND-REACTION
- Evidence `SRC-SYN-MIN/P1`: “Product yield was measured by calibrated GC using an internal standard.”

## Conditions

- **COND-REACTION:** 20 mg catalyst, 1.0 mmol substrate, 5 mL water, 80 °C for 6 h under 1 atm N2; yield measured by calibrated GC using an internal standard
  - `SRC-SYN-MIN/P1`: “All reactions used 20 mg catalyst, 1.0 mmol substrate, 5 mL water, 80 °C for 6 h under 1 atm N2. Product yield was measured by calibrated GC using an internal standard.”
- **COND-PRIOR:** Cited related catalyst at 100 °C; other experimental conditions not reported in the current excerpt
  - `SRC-SYN-MIN/P6`: “Chen et al. reported that a related catalyst could reach 90% yield at 100 °C”

## Uncertainties and non-promotion boundaries

- `bibliographic_limit`: The excerpt supplies only 'Chen et al.' and no bibliographic record; the cited original was not independently checked.
- `not_reported`: Explicit limitation establishes absence for the requested duration in this synthetic source; scalar, units, and statistic remain null because no measurement was reported. Claim layers: CL-LIM=limitation/declared_limitation.
- `epistemic_boundary`: limitation; modality=declarative; no promotion to established current-author fact
- `epistemic_boundary`: hypothesis_speculation; modality=speculative; no promotion to established current-author fact
- `epistemic_boundary`: prior_work_cited_claim; modality=reported_and_speculative; no promotion to established current-author fact

## Graph audit

Generated **23 nodes** and **29 directed edges**. `grounded_in` edges carry exact quotations; `supported_by` does not mean `proven`.
