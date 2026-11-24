# QA 报告 — synthetic-qa-demo-001

- 生成时间（UTC）: 2026-11-24T08:53:24+00:00
- 待检结果: `/Users/liuhengshen/Desktop/bhr_product/littrack-five/bundles/05-tracking-qa-harness/examples/minimal/candidate_result.json`
- 总体结论: **FAIL** — 存在阻断项，禁止交付：修复 blocking_items 后重跑全部门禁

## 各门禁状态

| 门禁 | 状态 | errors | warnings |
|---|---|---|---|
| contract_validate | pass | 0 | 0 |
| evidence_spotcheck | fail | 1 | 0 |
| freshness_check | fail | 2 | 0 |
| metrics | pass | - | - |

## 阻断项（blocking items）

1. **[evidence_spotcheck] item[2].locator** — new_items[2] (10.7554/elife.90001) locator 不可解析: 数组下标越界: 7（数组长度 2，pointer=/resultList/result/7）（locator: `materials/europepmc_response.json#/resultList/result/7`）
2. **[freshness_check] item[3].window** — new_items[3] (10.1016/j.cell.2026.08.015) 日期 2026-08-20 落在窗口 2026-10-01~2026-10-31 之外，且无 backfill 标记（不属于本窗口新增）
3. **[freshness_check] item[4].dedup** — new_items[4] (10.1038/s41586-026-00001-x) 已存在于 previous_snapshot（旧文重报，应去重）

## 警告项

（无）

## 指标

- `alert_precision` = 0.400
- `quarantine_rate` = 0.600
- `locator_resolvability` = 0.800
- `dedup_rate` = 0.200
- `window_coverage` = 0.600
- `window_coverage_strict` = 0.400
- `delivery_consistency` = 1.000

## 不确定项（uncertainty）

（无）
