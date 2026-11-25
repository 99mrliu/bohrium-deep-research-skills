# 任务 I/O 与产物 schema

## case.json

顶层必填：`case_id`、`sources`、`evidence`、`assertions`。ID 在各自命名空间唯一。表格 sources 使用 `source_type: table`；图注使用 `source_type: figure_caption`。

直接量值断言：

```json
{"assertion_id":"D01","kind":"direct","text":"…","value":"120","unit":"mentions","evidence_ids":["E01"]}
```

计算断言的通用结构：

```json
{
  "assertion_id":"C01", "kind":"calculated", "operation":"share",
  "operands":{"numerator":"120", "denominator":"400"},
  "operand_units":{"numerator":"mentions", "denominator":"mentions"},
  "operand_kinds":{"numerator":"mentions", "denominator":"mentions"},
  "operand_evidence_ids":{"numerator":["E01"], "denominator":["E02"]},
  "scope":{"numerator":"System A", "denominator":"All systems", "compatible":true},
  "rounding":{"places":1, "mode":"half_up"},
  "evidence_ids":["E01","E02"]
}
```

parts 使用 `operands.parts` 字符串数组、`operand_units.parts` 共同单位字符串、`operand_kinds.parts` 共同类型字符串、`part_evidence_ids` 二维数组。`sum_reconciliation` 还需 total；residual 使用 left/right。计算断言的 `evidence_ids` 必须恰好覆盖全部操作数引用（顺序不限）。

## task.md output_contract

仅解析标记间的一个 JSON code block：

~~~markdown
<!-- OUTPUT_CONTRACT_START -->
```json
{"required_result_fields":["case_id","status","assertion_results","summary","sources","uncertainty","change_records","run_metadata"],"required_calculation_fields":["case_id","status","calculations","direct_assertions","qualitative_assertions","unresolved"]}
```
<!-- OUTPUT_CONTRACT_END -->
~~~

已注册 result 字段：`case_id`、`status`、`assertion_results`、`summary`、`sources`、`uncertainty`、`change_records`、`run_metadata`、`artifacts`。已注册 calculations 字段：`case_id`、`status`、`calculations`、`direct_assertions`、`qualitative_assertions`、`unresolved`、`summary`。其他字段会报错而非猜值。

`case_id` 不可被 contract 改写。`sources` 汇总来源与 evidence 使用状态；`uncertainty` 收集未决及显式限制；`change_records` 记录每次断言状态变化。

## resources.yaml

```yaml
version: 1
limits:
  max_requests: 64
  max_seconds: 900
paths:
  work_dir: /app/work
  output_dir: /app/output
```

解析器只接受该两层字符串键值结构，不执行 YAML tag。CLI 显式路径优先于 paths；task contract 优先于所有默认输出字段。

## 退出码

- 0：全部直接、计算和质性断言处理完成，对账精确平衡。
- 2：可预期的数据、语义、契约或资源错误；尽量已保存 failed/partial 产物。
- 1：未预期内部错误。

示例 expected 文件均由命令真实生成。负例报告记录实际退出码及对应 failed result，不是手写“应当失败”的演示。
