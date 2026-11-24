# 事实核验报告（fact_check_report）

- 工具：fact_check 1.0.0（基于 ledger_extract 台账）
- 台账：`examples/expected/evidence_ledger.json`
- 改写稿：`examples/draft_good.md`
- 失败判定阈值（--min-severity）：mandatory
- 结论：**PASS**（退出码 0）

## 汇总

| 类别 | 条数 |
| --- | --- |
| unsupported_number（数字漂移/单位错配） | 0 |
| dropped_evidence（证据丢失） | 0 |
| strength_upgrade（论断强度升格） | 0 |
| **合计** | **0**（其中计入失败判定 0 条） |

核验覆盖面：改写稿数字 10 个；台账数字 10 个、图表引用 3 个、引用标记 3 个；论断句配对 4 组。

## 逐条发现

未发现 drift：改写稿通过全部核验。
