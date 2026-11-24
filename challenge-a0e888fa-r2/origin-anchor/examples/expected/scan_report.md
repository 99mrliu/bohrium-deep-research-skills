# 结构挖掘报告（table_scan）

- 源文件: `examples/trial_table.csv`
- sha256: `6c80cd8554295bbf570169c2a2e7b2f40f5ec1bd025b2a59be941c99244a738f`
- 规模: 5 个数据行 × 9 列
- 标签列: C0 `组别`
- 数值列: C1 `n`, C2 `male_n`, C3 `male_pct`, C4 `responders`, C5 `response_pct`, C6 `age_mean`, C7 `dose_mg_sum`, C8 `dose_mg_mean`
- 百分比列: C3 `male_pct`, C5 `response_pct`
- n 列: C1 `n`
- 合计行: R4 `合计`
- 小计行: R2 `小计(治疗)`
  - R2 `小计(治疗)` 的成员: R0 `A组`, R1 `B组`
- 叶行: R0 `A组`, R1 `B组`, R3 `安慰剂组`

## 下一步

- 请据数据字典填写 constraints.json（schema 见 references/aggregate_structures.md），然后运行 consistency_check.py。
