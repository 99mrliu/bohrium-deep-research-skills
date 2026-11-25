# SYNTHETIC 任务：不是正式结果

只依据 `examples/sources/study.md` 回答下列六个根问题及其 24 个子问题。所有数值都是合成数据，不得外推为真实临床结论。

- Q1 样本与主要结局：总样本、两组样本、主要结局。
- Q2 数值计算：四个量表换算、均值或百分比。
- Q3 谨慎推断：依从性、盲法、选择性、数据完整性。
- Q4 直接报告：随访窗口、试验时长、不良事件、分析原则。
- Q5 进一步计算与推断：两个计算、两个解释。
- Q6 未报告项目：药代动力学、生物标志物、生活质量、成本；必须记录检索范围。

```json
{
  "output_contract": {
    "mode": "EXACT",
    "fields": {
      "answers": {"type": "array"},
      "sources": {"type": "array"},
      "uncertainty": {"type": "array"},
      "change_records": {"type": "array"}
    }
  }
}
```

结果必须保留原 `case_id`，顶层只能有 `case_id` 和契约四字段。
