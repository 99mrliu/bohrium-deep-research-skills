# 论断对账报告（claim_audit）

> 合成示例 / SYNTHETIC EXAMPLE，非正式案例结果

## 摘要

- 论断总数：5
- supported：1
- unsupported：1
- conflict：1
- missing_source：0
- recorded_inferred：1
- recorded_missing：1
- 缺陷合计（unsupported+conflict+missing_source）：2
- 门禁结论：**拦截 BLOCK**

## 逐条结果

| # | plan_id | 字段 | status | verdict | char_offset | 说明 |
|---|---------|------|--------|---------|-------------|------|
| 0 | PLAN-A | resources.fbs_unit_price_cny | given | supported | 199 | quote 逐字命中 price_contract.txt（locator=条目 1, offset=199） |
| 1 | PLAN-A | parameters.fbs_percent | given | conflict | 266 | quote 已定位（offset=266），但 value 数值 [12.0] 与 quote 中数值 [10.0] 无交集 |
| 2 | PLAN-B | interpretation_criteria.doubling_time_hours | given | unsupported |  | quote 在 paper_excerpt.txt 中逐字查找失败（NFKC+空白折叠后） |
| 3 | PLAN-B | parameters.temperature_c | inferred | recorded_inferred |  | 模型推断值，仅记录，不参与判负；进入比较前须标注为假设 |
| 4 | PLAN-A | assumptions.ethics_approval | missing | recorded_missing |  | 方案未给出该字段，仅记录为缺口 |
