# SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE

这是一个完全虚构的 DSL 示例，不是官方赛题输入，也不代表真实文献结论。

Clean only according to the declarations below. Preserve missing observations.

Missing tokens: NA,N/A
Numeric fields: replicate
Identity keys: sample_id,batch

Numeric convention is supplied in this explicit rule-spec block:

```json rule-spec
{
  "rules": [
    {
      "id": "decimal-and-grouping-convention",
      "type": "parse_number",
      "field": "yield",
      "decimal": ".",
      "thousands": ","
    }
  ]
}
```
