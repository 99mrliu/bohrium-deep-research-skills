# result.json 合约

## case 中的声明

审计器和校验器共用同一个标准库解析器，支持以下显式 `output_contract` 形状。字段顺序按声明保留，同一列表内不得重复，字段名必须是非空字符串。

### 1. 数组或字段 mapping

数组中可写字段名，也可写带 `name` 的字段对象；数组声明的字段全部必填：

```json
{
  "case_id": "案例标识",
  "output_contract": [
    "case_id", "status", "sources", "uncertainty", "change_records",
    "data_quality",
    {"name": "task_specific_finding"}
  ]
}
```

直接 mapping 以键为字段名，值保留为字段定义；这种形状的字段同样全部必填：

```json
{
  "output_contract": {
    "data_quality": {"type": "array"},
    "limitations": {"type": "array"}
  }
}
```

### 2. fields / required_fields

`fields` 与 `required_fields` 均接受字段名数组、带 `name` 的对象数组，或以字段名为键的 mapping。只给其中一个时，其全部字段必填；两者同时给出时，`fields` 是全部声明字段，`required_fields` 是其中的必填子集：

```json
{
  "output_contract": {
    "fields": {
      "data_quality": {"type": "array"},
      "optional_note": {"type": "object"}
    },
    "required_fields": ["data_quality"]
  }
}
```

### 3. JSON Schema properties / required

可直接使用 JSON Schema 对象，也可置于 `schema` 或 `json_schema` 下。`properties` 的键是全部声明字段，`required` 是其中的必填子集；省略 `required` 表示这些属性均非合同必填项。`required` 中不得出现未在 `properties` 声明的名字。

```json
{
  "case_id": "案例标识",
  "output_contract": {
    "type": "object",
    "properties": {
      "case_id": {"type": "string"},
      "status": {"type": "string"},
      "sources": {"type": "array"},
      "uncertainty": {"type": "array"},
      "change_records": {"type": "array"},
      "data_quality": {"type": "array"},
      "optional_note": {"type": "object"}
    },
    "required": [
      "case_id", "status", "sources", "uncertainty", "change_records", "data_quality"
    ]
  }
}
```

这里只解析合同字段及必填关系，并不把校验器宣称为完整 JSON Schema 类型校验器。正式运行时以实际 case 为准，不假定示例字段。

## 顶层结构和标准字段

无论采用哪种合同形状，最终结果至少有：

- `case_id`：与 case 完全相等；
- `status`：只能是 `success` / `partial` / `unable` / `refused`，不能使用 `completed` 等第五种结果状态；
- `sources`、`uncertainty`、`change_records`：均为顶层数组；
- 合同 `required_fields`（或 JSON Schema `required`）中的每个字段直接置于顶层；
- 不得出现顶层 `output_contract` 键，更不得只在它里面保存答案字段。

`case_id`、`status`、`sources`、`uncertainty`、`change_records` **本身也可以是合同字段**，不算 collision，也不会被占位值覆盖；它们仍只在顶层出现一次并遵守上述标准约束。`output_contract` 不能作为答案字段，因为结果中禁止回显该嵌套键。

审计草稿会把**全部声明字段**平铺，包括 JSON Schema 中未列入 `required` 的可选属性。审计能产生 `data_identity`、`data_quality`、`split_audit`、`paper_claim_checks`、`method_comparison`、`limitations`；其他未知字段不会写成无解释的 null，而会写成结构化不可用说明，且结果保持 `partial`：

```json
{
  "status": "partial",
  "task_specific_finding": {
    "status": "unavailable",
    "reason": "The dataset audit does not produce this task-specific contract field.",
    "completion_required": true
  }
}
```

对应待办也会写入 `uncertainty`。这种占位不是事实证明，不能为了让结果变成 `success` 而保留。`success` 时所有必填合同字段必须非 null；校验器只检查基本结构，不判断一个非 null 值是否具有充分科学证据。

若合同没有 `limitations`，`report.md` 仍会列出 `audit.json` 中的范围限制，不会因读取不存在的 `result["limitations"]` 而崩溃；若该字段是结构化不可用对象，报告会保留其 JSON 说明。

## 方法比较与校验

正式完整交付的方法部分建议采用：

```json
{
  "status": "completed",
  "candidate_runs": [
    {"candidate_id": "A", "command": "...", "exit_code": 0, "environment": {}, "parameters": {}, "output": {}},
    {"candidate_id": "B", "command": "...", "exit_code": 0, "environment": {}, "parameters": {}, "output": {}}
  ],
  "predeclared_tolerance": {},
  "comparison": {},
  "attribution": {}
}
```

这里的 `method_comparison.status = completed` 是方法比较的子状态，不是允许的顶层结果状态。顶层为 `success` 且结果含 `method_comparison` 时，校验器要求该子状态为 `completed`、至少两个 `candidate_runs`，并存在 `predeclared_tolerance`、`comparison`、`attribution`。这是最低结构门槛，不可代替阅读日志与比较输出。

审计脚本永远只生成 `partial` 草稿和 `method_comparison.status = not_run`。正式 agent 必须实际运行两个候选后更新该字段；不可直接交付草稿冒充完整复现。

```bash
python3 scripts/check_result.py --case CASE.json --result RESULT.json
```

成功退出 0；JSON、合同形状、case_id、状态、顶层必填字段或 success 方法信息错误时输出错误并以 2 退出。缺 JSON Schema 必填字段会被拒绝，省略未列入 `required` 的可选属性可通过。900 秒时点前先保存满足顶层结构的 `partial`，再补充科学内容。

`examples/run_example.sh` 除原合成示例外，还实际运行 list 与 JSON Schema 正负例、标准字段入合同、未知字段占位、无 limitations 报告及其他解析形状测试。
