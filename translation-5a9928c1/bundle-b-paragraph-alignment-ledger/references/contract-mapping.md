# output_contract 字段映射（Bundle B）

| 合同字段 | 填充来源 |
|-|-|
| translated_text / translation | 全部已译块按段序拼接的完整译文 |
| bilingual / bilingual_pairs / alignment / paragraphs | [{id, kind, page, source, target, anchor}] |
| uncertainties / open_issues | 缺失段 + 不可读块 + 修复说明索引 |
| coverage / completeness | {translated, total, missing} |
| terminology / glossary | translations.json.terminology（若有） |
| evidence / sources / provenance | case.source_provenance |

未列出的必填键给最佳努力结构化值并写入 `extras` 说明；不得留空或用路径代替内容。
