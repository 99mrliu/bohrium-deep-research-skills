# 空白登记表（gap register）模板

> `gap_register.py` 的程序化产物为 `work/gap_register.json`；本模板用于模型人工
> 复核或补充登记时的书写格式。每行一条空白，字段缺一不得登记。

| gap_id | gap_type | description | docs_checked | binding_evidence |
| --- | --- | --- | --- | --- |
| G01 | single_source | 主题 '{theme} {label}' 仅由 {doc} 一篇文献覆盖，结论无法交叉验证 | [全部可用文献] | theme:{id}; sole_doc:{doc}; themes_source:{src} |
| G02 | unresolved_conflict | 议题 '{topic}' 上 {C1}({D1}, positive) 与 {C2}({D2}, negative) 方向相反，尚未裁决；并列登记，不做调和 | [{D1}, {D2}] | claim:C1; claim:C2 |
| G03 | facet_absent | facet '{category:value}' 在全部 {n} 篇可用文献中均未出现 | [全部可用文献] | facet_matrix.coverage[{facet}] = 0/{n} |

## 书写要求

1. `docs_checked` 必须列出实际查过的文献 id 清单；facet_absent / single_source
   为全部可用文献，unresolved_conflict 为冲突论断所在文献。
2. `binding_evidence` 必须可回链到机器产物（facet_matrix / claims.jsonl / themes.json）。
3. description 用具体对象+缺口类型表述；禁止"有待进一步研究""尚不明确""未来可期"
   等无绑定措辞。
4. 冲突并列登记，两方向各自标注来源；不得取多数、平均或调和。
5. 空白仅在本案语料内有界成立；语料外断言一律写入 uncertainties。
