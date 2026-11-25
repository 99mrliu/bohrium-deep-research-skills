# Comparison matrix

Case: `synthetic-estimand-case-001`
Task: `synthetic-decolorization-comparison-v1`

Descriptive comparison is retained even when estimands differ or cells are `not_reported`. Nothing in this matrix is a pooled estimate.

## Required preflight: task, metric, units, material, pollutant, budget

| estimand_id | task | metric | unit | material | pollutant | budget |
| --- | --- | --- | --- | --- | --- | --- |
| a-decolorization | ok | ok | ok | ok | ok | ok |
| b-adsorption | ok | ok | ok | ok | ok | not_reported |
| c-decolorization-hours | ok | ok | ok | ok | ok | ok |

`not_reported` is preserved and blocks quantitative gates; it does not erase this descriptive matrix.

## Corpus coverage (every document)

| source_document_id | path | paragraph_ids read | estimand_ids | coverage |
| --- | --- | --- | --- | --- |
| paper-a | corpus/paper-a.md | p1, p2, p3 | a-decolorization | read_in_full |
| paper-b | corpus/paper-b.md | p1, p2, p3 | b-adsorption | read_in_full |
| paper-c | corpus/paper-c.md | p1, p2, p3 | c-decolorization-hours | read_in_full |

## Evidence-backed normalized estimands

| estimand_id | source_document_id | outcome | metric | population | material | pollutant | intervention | condition | budget | time/horizon | unit/scale | estimate | stratum |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| a-decolorization | paper-a | decolorization of dye from synthetic textile wastewater | {"definition":"percentage reduction in baseline-corrected UV-vis absorbance at the dye peak","name":"decolorization_efficiency"} | batch photocatalytic test specimens | synthetic textile wastewater | Reactive Red 195 | UV/H2O2 treatment | batch; room temperature | {"unit":"min","value":90} | {"unit":"min","value":90} | {"scale":"percentage points on closed interval [0,100]","unit":"%"} | {"direction":"decrease","unit":"%","value":92} | d7bf440a3b00a4ed |
| b-adsorption | paper-b | removal of dye from aqueous solution | {"definition":"percentage reduction in measured aqueous Methylene Blue concentration from initial concentration","name":"adsorption_removal_fraction"} | batch adsorption test specimens | synthetic aqueous dye solution | Methylene Blue | activated carbon adsorption | batch; room temperature | {"unit":"not_reported","value":"not_reported"} | {"unit":"min","value":90} | {"scale":"percentage points on closed interval [0,100]","unit":"%"} | {"direction":"decrease","unit":"%","value":92} | e83713de09e51270 |
| c-decolorization-hours | paper-c | decolorization of dye from synthetic textile wastewater | {"definition":"percentage reduction in baseline-corrected UV-vis absorbance at the dye peak","name":"decolorization_efficiency"} | batch photocatalytic test specimens | synthetic textile wastewater | Reactive Red 195 | UV/H2O2 treatment | batch; room temperature | {"unit":"h","value":1.5} | {"unit":"h","value":1.5} | {"scale":"percentage points on closed interval [0,100]","unit":"%"} | {"direction":"decrease","unit":"%","value":92} | 9acabc05254a4514 |

## Exact source evidence

Each quote below is an exact substring of the cited source paragraph; no ellipsis or numeric rewriting is added.

### a-decolorization

Source: `paper-a`; paragraph: `p2`

> In a batch test at room temperature, synthetic textile wastewater containing Reactive Red 195 received UV/H2O2 treatment; after a 90 min observation horizon with a 90 min exposure budget, the decolorization efficiency, defined as the percentage reduction in baseline-corrected UV-vis absorbance at the dye peak, was 92%.

### b-adsorption

Source: `paper-b`; paragraph: `p2`

> In a batch test at room temperature, synthetic aqueous dye solution containing Methylene Blue contacted activated carbon; at a fixed 90 min observation horizon, the adsorption removal fraction, defined as the percentage reduction in measured aqueous Methylene Blue concentration from initial concentration, was 92%.

Source: `paper-b`; paragraph: `p3`

> The adsorbent-mass budget was not reported; a decrease in aqueous dye concentration was the qualitative direction.

### c-decolorization-hours

Source: `paper-c`; paragraph: `p2`

> In a batch test at room temperature, synthetic textile wastewater containing Reactive Red 195 received UV/H2O2 treatment; after a 1.5 h observation horizon with a 1.5 h exposure budget, the decolorization efficiency, defined as the percentage reduction in baseline-corrected UV-vis absorbance at the dye peak, was 92%.

## Raw stratum register

| sha256(stratum_key) | estimand_ids | canonical_key |
| --- | --- | --- |
| d7bf440a3b00a4ed1a2e6b1e6a8f3ca88a6863190fa9a6e9ab6c9d4eb7ab999c | a-decolorization | {"budget":{"unit":"min","value":"90"},"condition":"batch; room temperature","intervention":"UV/H2O2 treatment","material":"synthetic textile wastewater","metric":{"definition":"percentage reduction in baseline-corrected UV-vis absorbance at the dye peak","name":"decolorization_efficiency"},"outcome":"decolorization of dye from synthetic textile wastewater","pollutant":"Reactive Red 195","population":"batch photocatalytic test specimens","scale":"percentage points on closed interval [0,100]","task_id":"synthetic-decolorization-comparison-v1","time":{"unit":"min","value":"90"},"unit":"%"} |
| e83713de09e51270f2783b20c8caaaad867afabf9b8d356d1c9395037c0a2de1 | b-adsorption | {"budget":{"unit":"not_reported","value":"not_reported"},"condition":"batch; room temperature","intervention":"activated carbon adsorption","material":"synthetic aqueous dye solution","metric":{"definition":"percentage reduction in measured aqueous Methylene Blue concentration from initial concentration","name":"adsorption_removal_fraction"},"outcome":"removal of dye from aqueous solution","pollutant":"Methylene Blue","population":"batch adsorption test specimens","scale":"percentage points on closed interval [0,100]","task_id":"synthetic-decolorization-comparison-v1","time":{"unit":"min","value":"90"},"unit":"%"} |
| 9acabc05254a4514a7453f0176adf8433e414a2e2e5ca6aeb834abb91a16b08c | c-decolorization-hours | {"budget":{"unit":"h","value":"1.5"},"condition":"batch; room temperature","intervention":"UV/H2O2 treatment","material":"synthetic textile wastewater","metric":{"definition":"percentage reduction in baseline-corrected UV-vis absorbance at the dye peak","name":"decolorization_efficiency"},"outcome":"decolorization of dye from synthetic textile wastewater","pollutant":"Reactive Red 195","population":"batch photocatalytic test specimens","scale":"percentage points on closed interval [0,100]","task_id":"synthetic-decolorization-comparison-v1","time":{"unit":"h","value":"1.5"},"unit":"%"} |
