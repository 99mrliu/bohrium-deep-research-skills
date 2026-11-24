# 摄入审计报告

总体结论：**PASS**

| 检查项 | 状态 | 说明 |
|---|---|---|
| A1-per-file-closure | PASS | 每文件 items_found = parsed + quarantined；异常文件：无 |
| A2-total-closure | PASS | ledger={'files': 3, 'records_parsed': 11, 'items_quarantined': 2, 'duplicate_hints': 3} payload={'files': 3, 'records_parsed': 11, 'items_quarantined': 2, 'duplicate_hints': 3} actual=11/2 |
| A3-provenance-coordinates | PASS | 缺来源坐标的记录：无 |
| A4-field-status | PASS | field_status 缺失：无；missing-abstract=1 missing-title=0 |
| A5-encoding-trace | PASS | 非 utf-8 或有替换字符但无 decode_notes：无 |
| A6-dup-hint-integrity | PASS | 重复提示 3 条；悬空引用：无 |

## 总量
- 文件数：3
- 解析记录：11
- 隔离条目：2
- 精确重复提示：3

> 本报告由 ingest_audit.py 生成；计数可与 ingest_ledger.json 逐项对账。
