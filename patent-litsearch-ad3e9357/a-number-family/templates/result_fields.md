# result.json 字段口径（templates/result_fields.md）

| 字段 | 类型 | 口径 |
|-|-|-|
| `case_id` | string | 来自 case.json；缺失置 null 并写入 uncertainty |
| `status` | ok/partial/failed | ok=主管线全部完成且自查通过；partial=部分完成（必须写明未完成部分）；failed=无法完成（必须写明原因） |
| `candidates` | list | 每条：`raw`（原文号码）、`key`（规范键）、`ntype`、`kind`、`confidence`、`file`、`locator`、`match_type`（exact/related）、`warnings` |
| `families` | object | `scope_note`（双口径定义+限制声明）、`simple_families`、`extended_families`、`records`、`dedup_events`、`conflicts`、`records_without_priority` |
| `extracted_fields` | list | 每件传真的 `fields`（INID 名→{value, raw_segment}）与 `evidence_events` |
| `evidence_records` | list | 每条证据：file、locator（行号或 JSON 路径）、原文摘录 |
| `sources` | list | 每个来源：文件名/库名、类型、查询日期（ISO）、版本说明 |
| `uncertainty` | list | 歧义、缺失、未核验项、未填充契约字段 |
| `change_records` | list | 运行过程中的修正记录（时间、内容、原因） |
| `output_contract` | object | 镜像 case.json 的 output_contract 全部字段；未填充置 null 并在 uncertainty 说明 |

## merge_family 输入 records 格式

```json
{"records": [{"id": "rec1",
              "numbers": ["US 10,293,847 B2", "US 2018/0293847 A1"],
              "priorities": ["US 15/654,321"],
              "title": "...", "locator": "file:line 或 $.path"}]}
```

`numbers`/`priorities` 为原文号码串，规范化由脚本完成。
