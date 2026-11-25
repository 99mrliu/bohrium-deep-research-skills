# Synthetic scope mesh / 合成范围网格

**SYNTHETIC / 合成示例. Fictional Aster-17 study; no real-world claim or evidence. Structural checks are not semantic validation.**

## Bounded scope records

### R-POOLED — C-BOUNDED

- Classification: `demonstrated`
- `subject_population_material`: Thirty-two cast Aster-17 magnesium-alloy coupons from one fictional batch; 2.0 mm thick and 0.8 mm thin strata.
- `intervention_method`: Plasma-electrolytic oxidation (PEO), 18 V for 12 min.
- `comparator`: No coating, with the same salt-spray exposure.
- `dataset_sample`: 16 PEO and 16 uncoated coupons; eight of each thickness per arm; single fictional batch.
- `experimental_conditions`: 48 h salt-spray exposure at 35 °C with 5% NaCl; pooled endpoint measured immediately after exactly 48 h.
- `metric_unit`: Mean mass loss in g/m^2 after 48 h; no confidence intervals reported.
- `direction_effect`: Pooled mean mass loss was lower with PEO (6.4 g/m^2) than without coating (approximately 9.1 g/m^2).
- `limitations`: Pooled direction masks an opposite thin-coupon subgroup; one fictional alloy, batch, geometry pair, exposure, and endpoint only.
- Evidence: `source.txt [S3]` — “Across all coupons, mean mass loss was 6.4 g/m^2 in the PEO arm and approximately 9.1 g/m^2 in the uncoated arm.”

### R-THICK — C-BOUNDED

- Classification: `demonstrated`
- `subject_population_material`: The 2.0 mm thick stratum of cast Aster-17 magnesium-alloy coupons from the same fictional batch.
- `intervention_method`: PEO at 18 V for 12 min.
- `comparator`: Uncoated thick coupons under identical exposure.
- `dataset_sample`: Eight PEO and eight uncoated thick coupons within the 32-coupon laboratory dataset.
- `experimental_conditions`: 48 h salt-spray exposure at 35 °C with 5% NaCl.
- `metric_unit`: Mean mass loss in g/m^2 after 48 h; subgroup uncertainty not reported.
- `direction_effect`: Thick-coupon mean mass loss was 4.1 g/m^2 with PEO versus 10.2 g/m^2 without coating.
- `limitations`: Small fictional subgroup; no other thicknesses, batches, alloys, exposure durations, or field conditions tested.
- Evidence: `source.txt [S4]` — “thick PEO 4.1, uncoated 10.2”

### R-THIN — C-CONTRARY

- Classification: `demonstrated`
- `subject_population_material`: The 0.8 mm thin stratum of cast Aster-17 magnesium-alloy coupons from the same fictional batch.
- `intervention_method`: PEO at 18 V for 12 min.
- `comparator`: Uncoated thin coupons under identical exposure.
- `dataset_sample`: Eight PEO and eight uncoated thin coupons within the 32-coupon laboratory dataset.
- `experimental_conditions`: 48 h salt-spray exposure at 35 °C with 5% NaCl.
- `metric_unit`: Mean mass loss in g/m^2 after 48 h; subgroup uncertainty not reported.
- `direction_effect`: Contrary to the pooled direction, thin-coupon mean mass loss was higher with PEO (8.7 g/m^2) than without coating (7.9 g/m^2).
- `limitations`: Only eight coupons per arm; mechanism and statistical uncertainty not established; nevertheless this reported subgroup directly contradicts an always/all-subgroups claim.
- Evidence: `source.txt [S3]` — “In the thin stratum, mean mass loss was 8.7 g/m^2 with PEO and 7.9 g/m^2 without coating, reversing the pooled direction.”

### R-MECHANISM — C-MECHANISM

- Classification: `inferred`
- `subject_population_material`: 0.8 mm thin cast Aster-17 coupons compared with 2.0 mm thick coupons in the fictional study.
- `intervention_method`: Post hoc interpretation of the PEO thin-coupon reversal; no mechanistic intervention.
- `comparator`: Uncoated thin coupons and the thick-coupon stratum; no direct edge-effect comparator.
- `dataset_sample`: Same 32 coupons; no independent mechanistic dataset.
- `experimental_conditions`: Observed after 48 h salt spray at 35 °C with 5% NaCl; no morphology or edge-effect measurement reported.
- `metric_unit`: **NA** — The authors supplied speculation rather than a measured mechanistic endpoint or unit.
- `direction_effect`: A higher edge-to-face ratio may contribute to the observed thin-coupon reversal; direction and magnitude of any mechanistic contribution are not established.
- `limitations`: Explicit speculation only; no causal mechanism, morphology measurement, mediation analysis, or independent replication.
- `inference_reasoning`: The inferred mechanism is retained separately because the source says 'may contribute' and explicitly states that no mechanism was established.
- Evidence: `source.txt [S5]` — “The authors speculate that a higher edge-to-face ratio may contribute to the thin-coupon reversal, but no mechanism was established.”

### R-SERVICE — C-SERVICE

- Classification: `not_reported`
- `subject_population_material`: Service components, other alloys, and field environments beyond the tested fictional Aster-17 coupons.
- `intervention_method`: PEO service performance and comparison with other coating methods were not experimentally tested.
- `comparator`: **NR** — No field comparator, external coating method, or external dataset was reported in Methods, Results, Table 1, or Discussion.
- `dataset_sample`: The only dataset is the single-batch 32-coupon laboratory salt-spray study; no field or external-comparison sample.
- `experimental_conditions`: **NR** — No service-life duration, field environment, other-alloy condition, or external-benchmark condition was reported.
- `metric_unit`: **NR** — No service-life endpoint/unit or comparative-ranking metric was reported in any supplied section.
- `direction_effect`: **NR** — No service-life, other-alloy, field, or state-of-the-art direction/effect was reported.
- `limitations`: The laboratory mass-loss result cannot establish field durability, other-alloy performance, or a state-of-the-art ranking.
- `not_reported_basis`: Methods S1, Abstract S2, Results S3, Table 1 S4, and Discussion S5 were inspected; Discussion explicitly lists service life, other alloys, field environments, and rankings as untested.
- Evidence: `source.txt [S5]` — “The study was not designed to test service life, other alloys, field environments, or rankings against other coating methods.”

## Universal-claim closure

### C-UNIVERSAL

- Triggered statement: PEO always reduces mass loss in every Aster-17 subgroup and is state of the art on all datasets.
- Assessment: **unsupported_generalization**
- Flags: `UNIVERSAL_COUNTEREXAMPLE_FOUND, UNSUPPORTED_GENERALIZATION`
- Bounded restatement: In this single fictional batch of cast Aster-17 coupons exposed to 5% NaCl salt spray for 48 h at 35 °C, PEO lowered pooled mean mass loss versus no coating, but the 0.8 mm thin subgroup reversed direction; service-life and state-of-the-art claims are not reported.
- Section coverage:
  - methods: checked=True; anchor=S1; quote=“Thick coupons were 2.0 mm and thin coupons were 0.8 mm; each arm contained eight coupons of each thickness.”
  - results: checked=True; anchor=S3; quote=“In the thin stratum, mean mass loss was 8.7 g/m^2 with PEO and 7.9 g/m^2 without coating, reversing the pooled direction.”
  - tables: checked=True; anchor=S4; quote=“thin PEO 8.7, uncoated 7.9”
  - discussion: checked=True; anchor=S5; quote=“The study was not designed to test service life, other alloys, field environments, or rankings against other coating methods.”
- Exception-search terms: thin, thick, reversed, opposite, no mechanism, other alloys, field environments, rankings, all datasets
- Exception-search locations: Methods [S1], Abstract [S2], Results [S3], Table 1 [S4], Discussion [S5]
- Counterexample: `R-THIN`; disposition=`bounded_restatement`; reason=The in-scope 0.8 mm subgroup has higher mass loss with PEO, defeating 'always' and 'every subgroup'; the pooled result must not erase this exception.

## Adjudication caveat

The thin-coupon contrary subgroup defeats the universal statement. The bounded pooled result remains separate from that subgroup. No service-life, other-alloy, field-condition, or state-of-the-art conclusion is demonstrated. Automated checks do not decide whether evidence semantically supports these records.
