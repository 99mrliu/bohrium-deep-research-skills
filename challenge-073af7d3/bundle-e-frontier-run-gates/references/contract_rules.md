# 输出契约规则（contract_lint 判定依据）

`contract_lint.py --case FILE --result FILE [--evidence-matrix FILE]`：任一违规 exit 1，全部通过 exit 0。违规信息带 JSON 路径。

## 规则

- **R1 status 枚举**：`result.status ∈ {ok, partial, blocked_no_corpus, blocked_no_contract, failed}`，否则 `invalid_status $.status`。
- **R2 case_id 一致**：`result.case_id == case.case_id`，否则 `case_id_mismatch $.case_id`。
- **R3 字段齐全**：`case.output_contract.fields` 的每个字段必须出现在 result 顶层，否则 `missing_field $.<field>`。case.json 无 output_contract 时，linter 采用四个 canonical 字段（trend_summary / theme_evolution / representative_works / research_gaps）并在报告 notes 中注明该假设（不判违规，但运行方应在结果中记录同一假设）。
- **R4 空字段规则**：
  - 字段值为 `null` / `""` / `[]` / `{}` → `empty_field $.<field>` 违规（任何 status 下都违规——想表达"未完成"必须用带说明的占位对象，而不是留空）。
  - 字段为**占位对象**（dict 且仅含非空 `note` 键）：status 为 `partial` / `blocked_*` / `failed` 时合法；status 为 `ok` 时判 `placeholder_under_ok $.<field>` 违规（声称完成就不许有占位）。
  - 有实质内容（含 note 以外的键或非空数组）→ 通过。
- **R5 证据引用解析**：遍历 result 全部 JSON 树，凡出现 `{"record_id": "<id>"}`（record_id 为字符串的 dict），该 id 必须存在于证据矩阵（jsonl 或 json，行内 `record_id` 或 `id` 键），否则 `dangling_evidence <path>.record_id`。未提供 `--evidence-matrix` 时跳过解析但仍在报告中统计引用数。

## status 枚举语义

| status | 含义 |
| --- | --- |
| `ok` | 契约字段全部有实质内容，门全过 |
| `partial` | 部分字段为占位/有界完成；占位字段的 note 与 uncertainty 必须说清边界 |
| `blocked_no_corpus` | 检索为空或语料不可用；说明检索式与范围 |
| `blocked_no_contract` | 因契约本身原因无法继续（极少用；缺 output_contract 时优先走 canonical 默认而非 blocked） |
| `failed` | 运行失败；说明失败点与已保留的中间产物 |

## 证据引用格式

结论对象内嵌 `{"record_id": "<id>", ...}`；`<id>` 一一对应证据矩阵行。每条趋势/主题/代表作/空白结论至少回链一条。证据矩阵每行至少含 `record_id`、`title`、`year`、`fields_available`。

## partial-first 纪律

第 0 步即写出骨架 result.json（case_id + 全字段占位 + status=partial + provenance），每阶段完成后回填。任何时刻中断，/app/output/result.json 都是可过 lint 的诚实 partial。
