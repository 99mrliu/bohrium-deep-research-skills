# 论断对账报告（claim_audit）

> 合成示例 / SYNTHETIC EXAMPLE，非正式案例结果

## 摘要

- 论断总数：9
- supported：9
- unsupported：0
- conflict：0
- missing_source：0
- recorded_inferred：0
- recorded_missing：0
- 缺陷合计（unsupported+conflict+missing_source）：0
- 门禁结论：**通过 PASS**

## 逐条结果

| # | plan_id | 字段 | status | verdict | char_offset | 说明 |
|---|---------|------|--------|---------|-------------|------|
| 0 | PLAN-A | parameters.temperature_c | given | supported | 185 | quote 逐字命中 paper_excerpt.txt（locator=第1段（方法）, offset=185） |
| 1 | PLAN-A | parameters.fbs_percent | given | supported | 208 | quote 逐字命中 paper_excerpt.txt（locator=第1段（方法）, offset=208） |
| 2 | PLAN-A | parameters.medium_type | given | supported | 208 | quote 逐字命中 paper_excerpt.txt（locator=第1段（方法）, offset=208） |
| 3 | PLAN-A | interpretation_criteria.doubling_time_hours | given | supported | 288 | quote 逐字命中 paper_excerpt.txt（locator=第2段（结果）, offset=288） |
| 4 | PLAN-A | interpretation_criteria.viability_percent | given | supported | 310 | quote 逐字命中 paper_excerpt.txt（locator=第2段（结果）, offset=310） |
| 5 | PLAN-A | resources.fbs_unit_price_cny | given | supported | 199 | quote 逐字命中 price_contract.txt（locator=条目 1, offset=199） |
| 6 | PLAN-A | resources.medium_unit_price_cny | given | supported | 232 | quote 逐字命中 price_contract.txt（locator=条目 2, offset=232） |
| 7 | PLAN-A | resources.incubator_daily_cost_cny | given | supported | 202 | quote 逐字命中 booking_contract.txt（locator=条款 1, offset=202） |
| 8 | PLAN-B | parameters.fbs_percent | given | supported | 208 | quote 逐字命中 paper_excerpt.txt（locator=第1段（方法）, offset=208） |
