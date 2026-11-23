# 支持的 output_contract 子集（contract-pilot）

pilot validate/finalize 对 `output_contract` 做确定性校验，支持以下 JSON Schema 子集：

| 关键字 | 行为 |
|---|---|
| `type` | string/number/integer/boolean/array/object；数组写法（联合类型）取任一匹配；`number`/`integer` 拒绝布尔 |
| `required` | 对象必需字段，递归检查 |
| `properties` | 逐属性递归 |
| `items` | 数组元素递归 |
| `additionalProperties: false` | 多余字段给警告（不硬失败，避免误伤平台容忍的附加字段） |
| `enum` | 值必须在枚举内 |
| `pattern` | 字符串正则（re.search 语义） |
| `minItems` / `maxItems` | 数组长度 |
| `minLength` / `maxLength` | 字符串长度 |
| `minimum` / `maximum` / `uniqueItems` / `format` / `const` / `default` / `title` / `description` | 识别但不强制 |
| 其他关键字 | 警告 `unknown schema keyword`，不静默放行 |

## 诚实性检查（超出 schema 的部分）

- `case_id` 必须与 case.json 一致。
- 结果中每个 `null` 必须在 `null_reasons` 中有对应 JSON 路径与理由（`$.a.b[0]` 形式）。
- `status: success` 但存在硬问题 → 硬失败；finalize 会把这种情况降为 partial。
- `status: failed/refused` 必须带 `failure` 或 `reason`。

## 语义边界

pilot 不理解 `oneOf`/`allOf`/`$ref`/条件 schema；遇到时给警告并交给人工复核。校验通过 ≠ 内容正确：它只证明结构合法、状态诚实。
