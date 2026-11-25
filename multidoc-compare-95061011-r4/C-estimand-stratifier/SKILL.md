---
name: estimand-stratifier
description: Evidence-backed estimand normalization and operation-specific comparison gates for multi-document scientific comparison, including descriptive strata, exact transforms, ranking checks, exchangeability-aware pool blocking, and dynamic result contracts.
---

# Estimand Stratifier

Use this Skill when a multi-document task asks whether results can be described, compared by direction, ranked, exactly transformed, or pooled. Its center is **estimand-specific comparison and analysis-level stratification**, not a blanket six-dimension court. A mismatch can block RANK without blocking DESCRIBE.

## Required runtime workflow

1. Read `/input/case.json`, `/input/task.md`, `/input/comparison-workorder.json`, and **every** document under `/input/corpus/`. Do not let the workorder limit which source documents are read.
2. Identify each intended operation and normalize the evidence-backed estimands. An estimand comprises outcome/metric definition, population/material/pollutant, intervention/method, condition/budget, time/horizon, and unit/scale. Preserve exact `source_document_id`, `paragraph_id`, and contiguous source quote for every record.
3. Before quantitative synthesis, check task identity, metric definition, units, material, pollutant, and budget. Preserve `not_reported`; never impute a budget or pool unlike datasets/dyes because both show percent.
4. Write `/app/work/estimands.json` using [the schema reference](references/runtime-and-schemas.md). The agent supplies semantic records and operation requests; the deterministic script does not invent normalization.
5. Apply [estimand/gate definitions](references/estimands-and-gates.md) and [the exact unit-transform policy](references/units-and-transforms.md). DESCRIBE tolerates unlike measures; DIRECTION requires caveats; RANK needs one known compatible stratum; TRANSFORM needs a whitelisted exact conversion; POOL additionally needs strong explicit exchangeability.
6. Run:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 python3 scripts/compare_estimands.py --input /input --work /app/work --output /app/output
   ```

7. Deliver `/app/output/comparison-matrix.md`, `/app/output/comparison-operations.md`, and `/app/output/result.json`. Verify exact `case_id`, all original dynamic `output_contract` keys and their list/dict types, all-document matrix coverage, and actual `sources`, `uncertainty`, and `change_records`.

## Decision discipline

Unknown core values block quantitative operations but leave the descriptive matrix intact. Noncomparability is a valid completed result: status can be `success` with RANK/POOL blocked. Use `partial` only for incomplete work, not disagreement or heterogeneity. Optional missing mild moderators do not automatically make work partial. Never run automatic meta-analysis or fabricate heterogeneity statistics, precision, pooled effects, or exchangeability.

## Validation

Run the included synthetic three-paper example and standard-library tests locally:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_example.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

The example demonstrates equal percentages across different metrics/pollutants, exact min-to-hour conversion, an unreported budget, successful descriptive completion, and strict failure of fake pooling.
