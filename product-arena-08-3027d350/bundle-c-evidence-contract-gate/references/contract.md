# 交付契约说明（result.json 与三个报告）

## result.json 必备结构

```json
{
  "case_id": "<与 /input/case.json 完全一致>",
  "status": "success | partial | failed",
  "result": { "<output_contract 声明的每个字段>": ... },
  "evidence": { "quotes": "gate_report.json", "coverage": "coverage_ledger.json" },
  "sources": ["<源文本文件清单>"],
  "uncertainty": ["[not_reported] ...", "[cannot_judge] ...", "[material_conflict] ..."],
  "boundaries": { "not_reported": [], "cannot_judge": [], "material_conflict": [] },
  "handoff": ["<人工接管点，failed/partial 时必填>"],
  "change_record": ["<每次修订一行>"]
}
```

硬性规则（contract_check.py 逐条校验）：

1. `case_id` 与 case.json 一致；
2. `output_contract.fields` 中 `required: true` 的字段必须出现在 `result` 载荷中；
3. 字段值为空（null/""/[]/{}）时，`uncertainty` 必须出现该字段名的解释；
4. `status` 必须在枚举内；partial/failed 必须有 uncertainty 或 handoff；
5. `evidence` 或 `sources` 至少其一非空（结果必须可回指）。

## 三个报告的接口

| 报告 | 产出脚本 | 关键字段 | 消费方 |
|-|-|-|-|
| gate_report.json | verify_quotes.py | status / counts / verified / near_miss / missing / waived / violations | status_writer 摘要、人工复核 |
| coverage_ledger.json | coverage_ledger.py | status / raw_chars / kept_chars / dropped / unaccounted_pct | status_writer 摘要 |
| contract_report.json | contract_check.py | verdict / fails / warns / checks[] | 交付前最后关卡 |

## drops.jsonl 类别枚举

`header_footer`（页眉页脚）、`figure_pixels`（图片/图形区，无字符）、
`duplicate`（重复抽取，如跨页重复行）、`unreadable`（乱码/无法识别）、
`other_declared`（其他，需在 notes 说明）。未知类别归入 other_declared 并告警。

## claims.jsonl 字段

`id`（必填）、`quote`（必填，逐字原文）、`page`（建议，溯源用）、
`waiver`（true 时跳过命中要求）、`waiver_reason`（waiver 时必填，否则记违规）。
