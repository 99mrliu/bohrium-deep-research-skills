# Raw data and data-spec contract

## Files

CSV and TSV require a unique, non-empty header. JSON may be an array of row objects or `{ "rows": [...] }`; JSON objects/arrays must not contain NaN or Infinity. All text is UTF-8 (CSV/TSV may have a UTF-8 BOM). `format` can be `csv`, `tsv`, or `json`; otherwise the suffix is used.

The data spec's allowed top-level keys are **only**:

- `path`: raw dataset path, required;
- `format`: optional format override;
- `columns`: logical-to-raw column mapping, required;
- `filters`: optional array;
- `transforms`: optional object.

Any other key fails rather than smuggling derived statistics into the spec. Raw values naturally live in the raw data file, not the spec.

## Column mapping

Required logical fields: `sample`, `group`, `value`. Optional: `feature`, `replicate`, `p`. Example:

```json
{
  "path": "replicates.tsv",
  "format": "tsv",
  "columns": {
    "feature": "gene",
    "sample": "biological_sample",
    "group": "condition",
    "replicate": "technical_replicate",
    "value": "expression",
    "p": "source_p"
  },
  "filters": [
    {"column": "qc", "operator": "eq", "value": "PASS"}
  ],
  "transforms": {
    "value": [{"operation": "log2", "pseudocount": 1}],
    "log2FC": {"operation": "mean_ratio", "numerator_group": "Treated", "denominator_group": "Control", "pseudocount": 0},
    "neg_log10_p": {"operation": "neg_log10", "column": "source_p", "floor": 1e-300}
  }
}
```

All configured raw columns must exist before analysis. Missing sample/group/feature is invalid. Sample identity is scoped by feature and group. Reusing a sample ID in different groups defines different independent samples; the workorder/task should ensure this matches the experimental design.

## Filters

Rules only contain `column`, `operator`, and optional `value`. Operators:

- `eq`, `ne`: exact raw-cell comparison (CSV values remain strings);
- `in`: `value` is an array;
- `gt`, `ge`, `lt`, `le`: finite numeric comparison;
- `not_null`: non-empty raw cell.

Excluded rows, row checksums, and reasons are audited. If every row is excluded, the run fails. Required numeric/transform values in retained rows must be finite. Group/statistical missing behavior is defined in the visual reference below.

## Transforms

`transforms.value` is one operation object or an ordered array. Supported operations:

- `log2`, `log10`, `ln` with optional non-negative/otherwise finite `pseudocount`; adjusted value must be >0;
- `scale` with `factor`;
- `offset` with `offset`;
- `abs`.

`transforms.log2FC` supports:

- `{ "operation": "column", "column": "raw_log2fc" }`: finite values must be constant within each feature (within floating tolerance), avoiding arbitrary selection among contradictory rows;
- `{ "operation": "mean_ratio", "numerator_group": "...", "denominator_group": "...", "pseudocount": 0 }`: computed from independently derived group means for each feature; both adjusted means must be >0.

`transforms.neg_log10_p` is `{ "operation": "neg_log10", "column": "raw_p", "floor": 1e-300 }`. Raw p must be in [0,1] and constant within feature. p=0 is logged using the positive declared floor and `p_zero_clamped` is true in feature statistics. No t-test or other p-value is inferred from replicates.

## Derivation equations

For sample `i` with repeated retained transformed observations `x_ij`, its sample mean is `m_i = mean_j(x_ij)`. For a group of `n` independent sample means:

- mean = `sum(m_i) / n`;
- SD = `sqrt(sum((m_i - mean)^2)/(n-1))` for n≥2;
- SEM = `SD / sqrt(n)` for n≥2.

No weighting by number of technical replicates is applied. The raw and transformed values are both retained to make transform decisions inspectable.
