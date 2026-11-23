# notes.json 字段字典（source-fidelity-notes）

notes.json 是 Agent 手写的中间稿，`make_result.py` 据此装配 result.json。

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `result_fields` | object | 与 case `output_contract` 一一对应的交付内容；键名、嵌套与类型必须忠于合同 |
| `sources` | array | 输入材料清单：`[{doc_id, sha256, backend, path}]` |
| `null_reasons` | object | result_fields 中每个 null 的检索范围与理由，键为 JSON 路径如 `$.answer.q2` |
| `limits` | array of string | 受损页、未精读章节、合同外缺口 |
| `uncertainty` | array | 无法判断项：`[{topic, why, checked_at}]` |
| `change_records` | array | 修正记录：`[{what, before, after, why}]` |

## 论断条目（在 result_fields 内部）

每个关键论断写成对象：`{"claim": ..., "anchor": "p2-l14", "quote": "该行逐字片段", ...}`。
卡片类字段（方法、数据、局限）可用同构对象列表。无法核验：`"status":"unverifiable","reason":...` 并豁免锚点检查。

## 状态机（make_result.py 裁定）

- `success`：合同字段齐备、类型匹配、无“无理由 null”、锚点校验 pass、保真非 unreadable。
- `partial`：其余一切可交付情形，`limits` 必须逐项命名缺口。
- `failed`：文本层不可得（保真回执 unreadable）。

脚本只做装配与校验：不删字段、不改写内容、不自动升级状态。
