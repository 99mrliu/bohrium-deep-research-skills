# output_contract 绑定规则

## 契约形态兼容

`case.json` 的 `output_contract` 可能是三种形态，contract_scaffold.py / contract_validate.py 均兼容：

1. **对象**：`{"research_summary": "...", "evidence_matrix": "...", "uncertainty": "..."}` —— 键即字段名；
2. **数组**：`["research_summary", ...]` 或 `[{"name": "research_summary"}, ...]`；
3. **字符串**：按换行/逗号切分。

字段名**逐字照抄**，包括大小写、下划线、中英文；不得翻译、不得改成"更合理"的名字。

## 绑定纪律

- `case_id` 从 case.json 原样复制，字符串比对，不允许重打。
- 骨架字段顺序 = 契约声明顺序，便于人读核对。
- 契约未声明而运行需要的字段（status、provenance 等）可以添加，但必须在 contract_fields.md 中注明是运行状态字段，与契约字段区分。
- 契约字段的取值语义以契约中的说明文字为准；说明要求"数组"就不要给字符串。

## 状态语义

| status | 含义 | 前置条件 |
|---|---|---|
| success | 契约字段全部实质回填，结论与证据范围一致 | contract_validate 无硬失败 |
| partial | 有合法半成品，但存在材料缺失/无法判定项 | 缺口逐条写明在哪个字段、缺什么、为什么 |
| failed | 契约不可解析、输入不可用或运行中断 | 写明失败点 |

## 校验判定

contract_validate.py 的硬失败：case_id 不一致；契约字段缺失；status 非法；status=success 但存在未回填契约字段。警告（不判失败）：契约外字段；partial 但 uncertainty 为空。回填率（已实质回填契约字段占比）会写入校验报告，供评审核对增量交付质量。
