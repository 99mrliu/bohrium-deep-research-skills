# 原始 schema、字段映射与引用规则

## 1. 优先级与 EXACT 键

优先级从高到低：

1. 随任务 `/input/case.json` 给出的原始 `output_contract`；这是最终顶层 schema 的唯一权威。
2. `field_mapping` 中对输出字段到规范数据流的显式映射。
3. `manifest.output_fields` / `manifest.request_format`；它们只是输出声明，必须与契约一致，不能扩写或改写契约。
4. `contract_values` 中调用方已经提供的自定义必需字段值。
5. 工具内部的规范名称只用于处理，不可反向增加顶层键。

`output_contract` 可为字段名字符串数组，或：

```json
{
  "fields": ["case_id", "claims", "sources", "uncertainty", "change_records"],
  "additionalProperties": false
}
```

字段保序且不重复，必须含精确键 `case_id`。`manifest.output_fields` 要逐项相同。缺字段和多字段都失败；特别是 `status`、`debug_status`、`errors`、报告路径、分数等辅助信息不得塞入 `result.json`。`validation-report.json` 是独立文件，不属于结果 schema。

`case_id` 永远直接保留原值且不可重映射。其他字段示例：

```json
"field_mapping": {
  "assertion_records": "claims",
  "provenance_records": "evidence",
  "source_records": "sources"
}
```

上例要求这三个别名均列在原 `output_contract.fields` 和 manifest 中。允许的目标规范流为 `claims`、`evidence`、`sources`、`uncertainty`、`change_records`、`publications`，或 `contract_values`。未知输出字段若没有同名 `contract_values` 诚实值，报错而不是填 `null`、空字符串或编造对象。复杂条件 JSON Schema、任意嵌套转换不在本工具边界内，应交给专用转换步骤后再发布。

## 2. 通用规范化输入

顶层：

- `case_id`：非空字符串；
- `output_contract`、`manifest`：上述声明；
- 可选 `field_mapping`、`contract_values`；
- `claims`、`evidence`、`sources`：数组；即使当前输出契约不选择某个规范流，输入引用仍先完整校验。

每条 claim：

```json
{
  "claim_id": "c1",
  "subject": {"iri": "https://example.org/synthetic/s"},
  "predicate": {"iri": "https://example.org/synthetic/p"},
  "object": {"value": "synthetic object"},
  "evidence_ids": ["e1"],
  "polarity": "negative",
  "hedged": true,
  "hedge": "May not hold.",
  "condition": "Only in the synthetic test condition.",
  "uncertainty": "The synthetic wording is unresolved."
}
```

- claim subject/predicate 必须是显式 `iri` 对象；object 可用 `iri`，或字符串 `value` 加可选 `language` / `datatype`（二者互斥）。字符串不会被猜测为 IRI 或数值。
- `polarity` 只能为 `positive` / `negative`，缺省为 `positive`；`hedged` 必须为布尔量，缺省 false。`hedge` 文本出现时要求 `hedged=true`。condition/uncertainty 只保留明确给出的文本。
- 每条 evidence 含唯一 `evidence_id`、`source_ids`，可选原文 `text`；每个 source 含唯一 `source_id`，可选 `title`、`locator`。
- 每个 `claim.evidence_ids` 必须存在，每个 `evidence.source_ids` 必须存在；任何重复 ID 或悬空引用均失败。字段别名映射后仍按规范目标流复核，不能因重命名绕过检查。

## 3. 输出数据流与 partial

- `claims`：规范化 claim 及明确限定属性。
- `evidence`：规范化 evidence 及 source 引用。
- `sources`：仅输入实际提供的 source 数据。
- `uncertainty`：负面陈述、条件、hedge 和显式 uncertainty 的带 claim_id 记录；正面无条件且无显式不确定性时可为空数组。
- `change_records`：记录契约接受、引用规范化、完成三个阶段，含有意义的 partial/complete 状态，但整个顶层不能另加 status。
- `publications`：仅 RDF 请求生成的本地图连接记录；JSON/JSONL 请求若原契约声明此字段，则诚实为空数组，不生成 RDF 文件。

工具在解析并确认 EXACT 契约后、规范化 claims 之前，就向 work 写 `result.partial.json`。此刻 claims/evidence/sources 为空，uncertainty 和 change_records 明示“不完整”；规范化引用后再次写 partial。候选结果通过独立回读后才进入 output。若原契约本身不合法，无法构造安全 partial，所以只写 `publish-error.json` 并声明未宣称完成。

## 4. 请求格式与禁止额外交付

`manifest.request_format` 只接受：

- `json`：`result.json` + 独立 `validation-report.json`；不输出 RDF，也不输出 JSONL。
- `jsonl`：再输出 `claims.jsonl`，一行一 claim；回读行数、重复键和每条内容；不输出 RDF。
- `rdf`：再输出 `nanopubs.trig` 和 `nanopubs.jsonld`，并对同一四图模型做回读、关键结构和引用检查。

所有格式都以原契约的 `result.json` 为基础。JSON 使用 UTF-8，拒绝重复键；重要结果读取回来后再比对，而不是仅验证内存对象。
