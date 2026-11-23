# Delivery schema reference

本文件定义 `bundle-e-contract-auditor` 的下游交付契约。所有文件为 UTF-8 文本；运行脚本只依赖 Python 3.10+ 标准库。

## 1. 顶层 `result.json`

核心字段始终存在：

| 字段 | 类型 | 规则 |
|---|---|---|
| `schema_version` | string | 当前为 `1.0.0` |
| `case_id` | string/null | 从 case 的 `case_id`/`id` 等字段取得；不可得时为 null，不编造 |
| `result` | object | 主结果摘要、表文件、行数、表头和 review 数 |
| `status` | string | `success`、`partial`、`input_error` 之一 |
| `sources` | array | 输入 case、声明 CSV、task 的路径、角色、行数和 SHA-256 |
| `uncertainty` | array | blocking/error/warning 异常与人工接管点；无证据项不得写成事实 |
| `change_records` | array | 与 `changes.jsonl` 相同的逐单元格变更记录 |
| `coverage` | object | `counts` 与逐输入行 `rows` 覆盖证明 |
| `artifacts` | object | 固定 artifact 逻辑名到相对文件名的映射 |
| `unresolved_fields` | array | 已声明但无确定性适配器的契约字段及原因 |

### 1.1 `output_contract` 适配器

契约可来自 case 的 `output_contract`，也可来自 task 中的 JSON 或字段列表。适配器支持三种形态：

```json
{"properties": {"case_id": {"type": "string"}, "extra_key": {"type": "null"}}, "required": ["case_id", "status"]}
```

```json
["case_id", {"name": "result"}, "status: string"]
```

```text
case_id, result (object), status (string), extra_null
```

已知键直接填充：`case_id`、`result`、`status`、`sources`、`uncertainty`、`change_records`、`coverage`、`artifacts`，以及 `answer/summary`、`cleaned_data/cleaned_records/table`、`anomalies`、`review_queue`、`validation`、`row_count` 等明确同义词。

未知但已声明的键不猜值：写入 `null`，并加入：

```json
{"field": "extra_key", "reason": "declared output_contract field has no deterministic adapter in this skill; left null rather than fabricated"}
```

核验器要求这些 null 键必须列入 `unresolved_fields`。

## 2. 主统计表

`cleaned.csv` 与 `cleaned.json` 内容等价。所有行使用同一 header；CSV 空字符串表示 JSON null。

基础列：

- 身份/定位：`input_row_id`、`source_pointer`、`row_status`、`record_id`、`source_id`
- 科学字段：`substance`、`property`、`value`、`unit`、`value_min`、`value_max`
- 原值与换算：`raw_value`、`raw_unit`、`conversion_rule`、`conversion_formula`、`conversion_factor`、`conversion_offset`、`conversion_change_id`、`source_decimal_places`
- 原始行绑定：`source_record_sha256`
- 证据定位：`page`、`paragraph`、`table`、`figure`、`conditions`、`context`
- 未映射来源列：`unmapped__<safe_name>`，原值保留，语义不猜

规则：

1. `value` 只能是有限浮点数或 null；CSV/JSON 不得出现 NaN 或 Infinity。
2. 未知单位时 `value=null`、`unit=null`，原始文本只留在 `raw_value/raw_unit`。
3. 坏数字时 `value=null`，原样保留在 `raw_value`。
4. 缺值 marker 统一为 null，并保持 `MISSING_VALUE` warning。
5. 区间拆成 `value_min/value_max`；`value` 保持 null，不伪造 midpoint。
6. `row_status` 只有 `kept` 或 `flagged`。deduplicated/rejected 行不进主表，必须在 coverage 中说明。

## 3. 覆盖证明

`coverage.counts`：

```json
{"total": 8, "kept": 1, "flagged": 6, "deduplicated": 1, "rejected": 0}
```

不变式：

```text
total = kept + flagged + deduplicated + rejected
cleaned_rows = kept + flagged
len(coverage.rows) = total
```

每个 `coverage.rows[]`：

| 字段 | 含义 |
|---|---|
| `input_row_id` | 稳定 R000001... 输入行 ID |
| `source_pointer` | 输入文件加 JSON/CSV 路径 |
| `source_record_sha256` | 展平前原始记录稳定 JSON 的 SHA-256 |
| `disposition` | 四种互斥处置之一 |
| `output_row_id` | retained 行的 O000001...；未 retained 为 null |
| `duplicate_of` | D001 自动去重时指向保留的输入行 |
| `reason` | rejected/deduplicated 的机器理由 |

## 4. 异常和 review 文件

`anomalies.csv` 列：`anomaly_id,severity,code,input_row_id,source_pointer,field,rule_id,message,details,affected_rows`。

严重度：

- `blocking`：输入不可用或交付机器完整性失败。
- `error`：不能自动安全标准化的单元格/列/身份冲突。
- `warning`：保留但需人工确认的不确定性。
- `info`：确定性、无数据损失的动作。

`review_queue.csv` 只包含 blocking/error/warning 中需要接管的问题，另加 `review_id`、`suggested_action`、`status=open`、`resolution`、`owner`。它不是异常副本，而是人工闭环队列。

## 5. `changes.jsonl`

每行一个 JSON：

```json
{
  "change_id": "C000005",
  "rule_id": "U002",
  "input_row_id": "R000001",
  "source_pointer": "case.json#datasets/0/records/0",
  "raw_field": "value",
  "field": "value",
  "before": "25",
  "after": 298.15,
  "action": "unit_convert",
  "reason": "°C converted to K with recorded formula",
  "conversion": {
    "raw_value": "25",
    "raw_unit": "°C",
    "target_unit": "K",
    "factor": null,
    "offset": null,
    "formula": "x0 = raw + 273.15; x_base = x0; target = x_base",
    "output": 298.15
  }
}
```

规则族：

- `S001-S004`：字段映射、标量规范化、同义列冲突、不猜映射。
- `V001-V004`：缺值、数值解析、区间拆分、坏数字。
- `U001-U004`：单位别名、公式换算、未知单位、缺单位。
- `D001-D003`：可解释自动去重、ID 冲突、潜在重复实验。
- `B001/C001/I001-I003`：预算、覆盖、输入边界。

## 6. 完整性与原子写

写文件顺序：先写 payload，再写 checksum，再写 manifest，最后由 verify 写 validation。所有文件通过同目录临时文件加 `os.replace` 原子替换。

`checksums.sha256` 覆盖：`cleaned.csv`、`cleaned.json`、`anomalies.csv`、`review_queue.csv`、`changes.jsonl`、`audit.md`、`result.json`。

`manifest.json.files[]` 记录这些 payload 的相对路径、字节数和 SHA-256；`manifest.json.checksums_file` 再绑定 `checksums.sha256`。`manifest.json` 和 `validation.json` 显式列出为不由 manifest 自哈希，避免循环依赖。移动或修改任何 payload 后必须重新 `verify`。

## 7. 退出码

| 命令 | 退出码 | 含义 |
|---|---:|---|
| `run` | 0 | 清洗完成且独立终检无 blocking；status 可为 success 或 partial |
| `run` | 2 | 输入失败，已写 `input_error`/partial 工件 |
| `run` | 3 | 产物终检出现 blocking |
| `verify` | 0 | 无 blocking；可存在如实记录的源数据 error findings |
| `verify` | 3 | 合同、覆盖、追踪、非有限数、manifest 或 checksum blocking 失败 |
