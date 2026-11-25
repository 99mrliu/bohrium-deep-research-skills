# output_contract 字段映射（Bundle A）

result.json 必须含 `case_id`、`status`（success/partial/failed 按合同枚举）及合同
`output_contract.required` 的每一个键。常见映射：

| 合同字段 | 填充来源 |
|-|-|
| translated_text / translation | 全部已译段按原文顺序拼接的完整译文 |
| bilingual / bilingual_pairs / alignment | [{id, source, target, zone}] 段落级对照 |
| terminology / glossary / terms | 锁定术语表（含决议与禁用变体） |
| uncertainties / open_issues / human_confirm | 审计 human_confirm + 未译段 |
| evidence / sources / provenance | case.source_provenance + 实际源文件 sha256 |
| revisions / change_log | history 段（决议与重锁记录） |

合同若要求未列出的键，assemble_result 给最佳努力结构化值并在 `extras` 说明，
不得留空、不得用文件路径代替内容。
