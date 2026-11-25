# Claim-scope and conflict-mechanism atlas

This atlas is not a `+1/-1` claim graph. Lexical polarity is not scientific agreement, and condition differences are not causal attribution.

## Exact-key proposition clusters

exact agent-specified proposition_key only; no fuzzy/entity matching

- `mb-capacity-composite-vs-control-ambient`: `P-A-AMBIENT`, `P-B-AMBIENT`, `P-C-AMBIENT`
- `mb-capacity-composite-vs-control-acidic-extension`: `P-B-ACIDIC`
- `mb-capacity-ph-moderator`: `P-C-MODERATOR`
- `mb-capacity-micropore-speculation`: `P-A-PORE-SPECULATION`

## Propositions, evidence kinds and limitations

### P-A-AMBIENT

- **Tuple:** dye adsorption capacity / magnetite-biochar vs pristine biochar / equilibrium adsorption capacity (mg/g) / `scoped`.
- **Exact key:** `mb-capacity-composite-vs-control-ambient`.
- **Material / pollutant / task:** ["magnetite-biochar", "pristine biochar"] / ["methylene blue"] / batch adsorption removal.
- **Applicability:** {"applicability": "ambient laboratory comparison only", "contact_time": {"unit": "min", "value": 120}, "dose": {"unit": "g/L", "value": 1}, "initial_concentration": {"unit": "mg/L", "value": 100}, "pH": 7, "temperature": {"unit": "K", "value": 298}}.
- **Evidence:** `A-E1` (observed_result; `paper-a`, `a-p2`).
- **Direction:** increase.
- **Strength wording:** numerically larger capacity in this batch. **Statistical significance:** not_reported.
- **Reported measurements (not pooled):** magnetite-biochar: 120 mg/g; pristine biochar: 80 mg/g.
- **Within-paper limitations:** Single independently prepared laboratory batch.; No statistical significance test reported.; No basis for generalization to other dyes or preparations..

### P-B-ACIDIC

- **Tuple:** dye adsorption capacity / magnetite-biochar vs pristine biochar / equilibrium adsorption capacity (mg/g) / `scoped`.
- **Exact key:** `mb-capacity-composite-vs-control-acidic-extension`.
- **Material / pollutant / task:** ["magnetite-biochar", "pristine biochar"] / ["methylene blue"] / batch adsorption removal.
- **Applicability:** {"applicability": "acidic extension only", "contact_time": {"unit": "min", "value": 120}, "dose": {"unit": "g/L", "value": 1}, "initial_concentration": {"unit": "mg/L", "value": 100}, "pH": 3, "relation_role": "scope_extension", "temperature": {"unit": "K", "value": 298}}.
- **Evidence:** `B-E1` (observed_result; `paper-b`, `b-p2`).
- **Direction:** not assigned; not warranted.
- **Strength wording:** small numerical separation without equivalence or uncertainty evidence. **Statistical significance:** not_reported.
- **Reported measurements (not pooled):** magnetite-biochar: 52 mg/g; pristine biochar: 50 mg/g.
- **Within-paper limitations:** No equivalence test or uncertainty interval.; Acidic scope cannot adjudicate the ambient result..

### P-B-AMBIENT

- **Tuple:** dye adsorption capacity / magnetite-biochar vs pristine biochar / equilibrium adsorption capacity (mg/g) / `scoped`.
- **Exact key:** `mb-capacity-composite-vs-control-ambient`.
- **Material / pollutant / task:** ["magnetite-biochar", "pristine biochar"] / ["methylene blue"] / batch adsorption removal.
- **Applicability:** {"applicability": "ambient attempted replication only", "contact_time": {"unit": "min", "value": 120}, "dose": {"unit": "g/L", "value": 1}, "initial_concentration": {"unit": "mg/L", "value": 100}, "pH": 7, "temperature": {"unit": "K", "value": 298}}.
- **Evidence:** `B-E2` (observed_result; `paper-b`, `b-p3`).
- **Direction:** decrease.
- **Strength wording:** numerically lower composite capacity in this independent replication. **Statistical significance:** not_reported.
- **Reported measurements (not pooled):** magnetite-biochar: 65 mg/g; pristine biochar: 90 mg/g.
- **Within-paper limitations:** Independent synthesis batch.; No mechanism moderator tested.; No statistical significance test reported..

### P-C-AMBIENT

- **Tuple:** dye adsorption capacity / magnetite-biochar vs pristine biochar / equilibrium adsorption capacity (mg/g) / `scoped`.
- **Exact key:** `mb-capacity-composite-vs-control-ambient`.
- **Material / pollutant / task:** ["magnetite-biochar", "pristine biochar"] / ["methylene blue"] / batch adsorption removal.
- **Applicability:** {"applicability": "ambient arm of direct material-by-pH comparison", "contact_time": {"unit": "min", "value": 120}, "dose": {"unit": "g/L", "value": 1}, "initial_concentration": {"unit": "mg/L", "value": 100}, "pH": 7, "temperature": {"unit": "K", "value": 298}}.
- **Evidence:** `C-E1` (observed_result; `paper-c`, `c-p2`).
- **Direction:** increase.
- **Strength wording:** numerically larger ambient capacity within the direct comparison. **Statistical significance:** not_reported.
- **Reported measurements (not pooled):** magnetite-biochar, pH 7: 118 mg/g; pristine biochar, pH 7: 82 mg/g; magnetite-biochar, pH 3: 51 mg/g; pristine biochar, pH 3: 49 mg/g.
- **Within-paper limitations:** One preparation protocol.; No statistical significance test reported.; Does not test the source of Paper B's divergence..

### P-C-MODERATOR

- **Tuple:** moderation of dye adsorption capacity / material type x pH / equilibrium adsorption capacity (mg/g) / `scoped`.
- **Exact key:** `mb-capacity-ph-moderator`.
- **Material / pollutant / task:** ["magnetite-biochar", "pristine biochar"] / ["methylene blue"] / direct head-to-head moderator test.
- **Applicability:** {"applicability": "tested material-by-pH domain only", "held_constant": ["initial concentration 100 mg/L", "298 K", "120 min", "1 g/L"], "pH_levels_tested": [3, 7]}.
- **Evidence:** `C-E1` (observed_result; `paper-c`, `c-p2`).
- **Direction:** not assigned; not warranted.
- **Strength wording:** direct four-arm pattern consistent with pH moderation. **Statistical significance:** not_reported.
- **Reported measurements (not pooled):** magnetite-biochar, pH 7: 118 mg/g; pristine biochar, pH 7: 82 mg/g; magnetite-biochar, pH 3: 51 mg/g; pristine biochar, pH 3: 49 mg/g.
- **Within-paper limitations:** Ionic strength not independently varied.; Surface charge not measured.; Bounded to tested materials and pH levels..

### P-A-PORE-SPECULATION

- **Tuple:** proposed origin of capacity difference / micropore-area explanation vs alternatives / mechanistic evidence (not_applicable) / `scoped`.
- **Exact key:** `mb-capacity-micropore-speculation`.
- **Material / pollutant / task:** ["magnetite-biochar", "pristine biochar"] / ["methylene blue"] / mechanism interpretation.
- **Applicability:** {"applicability": "author hypothesis for Dataset A; no direct mechanism measurement"}.
- **Evidence:** `A-E2` (speculation; `paper-a`, `a-p3`).
- **Direction:** not assigned; not warranted.
- **Strength wording:** explicitly speculative. **Statistical significance:** not_applicable.
- **Reported measurements (not pooled):** unreported / not applicable.
- **Within-paper limitations:** Micropore area not measured.; Pore blocking, surface charge, and bonding not measured..

## Conflict verdicts

Only explicitly supplied proposition pairs are evaluated.

| Relation | Propositions | Verdict | Evidence-bounded rationale | Quantitative compatibility |
|---|---|---|---|---|
| R1 | P-A-AMBIENT / P-B-ACIDIC | **complements** | The acidic proposition explicitly extends scope; it does not negate or replicate the ambient estimand. | allowed=false; budget is unreported or different; applicability scopes differ; unlike or unidentified datasets; quantitative synthesis is not authorized |
| R2 | P-A-AMBIENT / P-B-AMBIENT | **genuine_conflict** | The task, comparison, pollutant, metric, units, and stated ambient conditions match, but observed directions are opposite. Batch causality remains unresolved. | allowed=false; budget is unreported or different; unlike or unidentified datasets; quantitative synthesis is not authorized |
| R3 | P-A-AMBIENT / P-C-AMBIENT | **corroborates** | Both scoped ambient observations show the same ordered direction; this is qualitative corroboration, not pooled significance. | allowed=false; budget is unreported or different; unlike or unidentified datasets; quantitative synthesis is not authorized |

## Mechanism attribution

A mechanism is a hypothesis unless directly tested. Supporting and alternative explanations are both retained.

### M-PH-MODERATOR: `supported_by_direct_comparison`

Within Paper C's tested domain, pH moderates the magnetite-biochar capacity benefit.

**Supporting explanations**
- The direct four-arm material-by-pH comparison holds the stated non-pH conditions fixed and tests the moderator. Evidence: ["C-E1"]; tested_by: `C-D1`.

**Alternative explanations**
- Ionic strength or unmeasured surface-charge pathways may contribute; neither was independently tested. Status: `unresolved`; evidence: [].

**Direct comparisons**
- `C-D1` tests `pH` via `direct_head_to_head`; source `paper-c`, paragraph `c-p2`; held constant: ["initial concentration", "temperature", "contact time", "dose", "preparation protocol"].

### M-PORE-SPECULATION: `unresolved`

Increased micropore area is a possible cause of the Dataset A capacity difference, not an established attribution.

**Supporting explanations**
- Paper A authors propose micropore area, explicitly as speculation. Evidence: ["A-E2"]; tested_by: `unreported`.

**Alternative explanations**
- Surface charge, pore blocking, and bonding remain unmeasured alternatives. Status: `unresolved`; evidence: [].

### M-BATCH-EXPLANATION: `unresolved`

Independent synthesis batches might explain the A-versus-B ambient conflict, but condition differences alone do not establish that cause.

**Supporting explanations**
- Paper B identifies independent preparation as a candidate explanation only. Evidence: ["B-E3"]; tested_by: `unreported`.

**Alternative explanations**
- Unmeasured surface chemistry, pH history, or other procedural differences could explain the result. Status: `unresolved`; evidence: [].

## Concise integrated response

The records do not support a universal claim that magnetite-biochar improves dye adsorption. Paper B's acidic result complements the ambient literature by extending scope. Under matched reported ambient conditions, Papers A and B show opposite observed directions: this is a genuine_conflict and remains unresolved; batch preparation is only an untested candidate explanation. Paper C's ambient arm qualitatively corroborates Paper A, while its direct material-by-pH comparison supports bounded pH moderation. Paper C does not resolve the A-B replication conflict. The micropore explanation remains speculation. Statistical significance and budgets are unreported where stated, and no effect sizes, datasets, scopes, or dyes are pooled.
