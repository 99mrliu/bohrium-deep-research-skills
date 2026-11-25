# output_contract 字段映射（Bundle C）

| 合同字段 | 填充来源 |
|-|-|
| translated_text / translation | 全部已译段按序拼接的完整译文 |
| bilingual / bilingual_pairs / alignment | [{id, source, target, issues}]（issues 为该股审计差异） |
| uncertainties / open_issues / human_confirm | 全部审计差异（含 unit_convention 与 explained）+ 未译段 |
| verification / quality_check / audit | 审计摘要计数 |
| evidence / sources / provenance | case.source_provenance |
| terminology / glossary | translations.json.terminology（若有） |

未列出的必填键给最佳努力结构化值并写入 `extras`；`audit` 摘要始终随附。
