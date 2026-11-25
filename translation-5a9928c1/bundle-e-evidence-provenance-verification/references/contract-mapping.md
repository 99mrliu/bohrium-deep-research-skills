# output_contract 字段映射（Bundle E）

| 合同字段 | 填充来源 |
|-|-|-|
| translated_text / translation | 全部已译段按序拼接的完整译文 |
| bilingual / bilingual_pairs / alignment | [{id, source, target, evidence{quote,offset,verdict}, basis, note}] |
| uncertainties / open_issues / human_confirm | 不确定性登记册（逐条 segment+type+detail） |
| evidence / provenance | case.source_provenance + evidence_map（随附） |
| verification / quality_check | verification{status, register}（随附） |
| terminology / glossary | translations.json.terminology（若有） |

`evidence_map` 与 `verification` 始终随附，即使合同未列出。
