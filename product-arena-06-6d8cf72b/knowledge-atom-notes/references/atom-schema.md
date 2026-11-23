# atoms.json Schema（knowledge-atom-notes）

## 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `atoms` | array | 知识点条目，见下 |
| `contract_fields` | object | 与 case `output_contract` 对应的交付内容（键名/嵌套忠于合同） |
| `merges` | array | 归并留痕：`[{canonical, merged_ids, kept_id, why}]` |
| `sources` | array | `[{doc_id, sha256, backend}]` |
| `uncertainty` / `limits` | array | 无法判断项与缺口命名 |

## atom 通用字段

| 字段 | 说明 |
|---|---|
| `id` | 稳定 id，如 `m-01`、`f-03`；被 contract_fields 引用 |
| `type` | concept / method / finding / limitation / variable |
| `aliases` | 同义表述、缩写、大小写变体 |
| `evidence` | `[{anchor: "s2¶3", quote: "段落逐字片段"}]`；不可核验时省略并写 `not_reported: {"searched": ...}` |
| `conditions` | 让结论成立的前提（finding 强烈建议填写） |

## 类型必填字段

| type | 必填 | 可选 |
|---|---|---|
| concept | `term`, `definition` | `aliases` |
| method | `term`, `purpose` | `inputs`, `outputs`, `parameters` |
| finding | `claim` | `metric`, `value`, `comparator`, `conditions` |
| limitation | `claim`, `scope` | — |
| variable | `symbol`, `meaning` | `unit`, `value`, `range` |

## 锚点

`s{章节号}¶{段落号}`，均从 1 起；章节号与段落号以 sections.json 为准。quote 必须是该段落文本的逐字子串（空白归一化后）。
