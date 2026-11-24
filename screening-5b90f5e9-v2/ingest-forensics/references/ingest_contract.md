# 摄入产物契约（ingest_contract）

## records_ingested.json

```json
{
  "records": [
    {
      "record_id": "ingest-0001",
      "source_file": "pubmed_export.csv",
      "source_line": 2,
      "source_format": "csv",
      "encoding": "utf-8",
      "title": "...", "authors": "...", "year": "...", "journal": "...",
      "doi": "...", "doi_norm": "...", "abstract": "...", "pmid": "...",
      "field_status": ["ok"],
      "repair_notes": ["suspected-mojibake-in:title"]
    }
  ],
  "quarantine": [
    {"source_file": "scopus_export.json", "item_index": 2,
     "reason": "json-entry-not-object", "excerpt": "..."}
  ],
  "duplicate_hints": [
    {"key": "doi:10.0000/synth.2023.001", "kept": "ingest-0001",
     "also": "ingest-0011", "note": "exact-duplicate-hint; ..."}
  ],
  "totals": {"files": 3, "records_parsed": 11, "items_quarantined": 2,
             "duplicate_hints": 1},
  "provenance_policy": "每条记录含 source_file+source_line；..."
}
```

约束：

- `record_id` 按解析顺序单调编号，重跑同一目录结果一致（确定性）；
- `quarantine[].reason` 必须是机器可过滤的短码加必要说明；
- `duplicate_hints` 只登记精确键冲突（归一 DOI / 归一标题），**不做合并**——
  合并是下游去重环节的决定，此处保留全部副本与提示。

## ingest_ledger.json

```json
{
  "files": [
    {"source_file": "...", "bytes": 0, "lines": 0, "encoding": "utf-8",
     "replaced_chars": 0, "decode_notes": [], "format": "csv",
     "records_parsed": 5, "items_quarantined": 0, "items_found": 5}
  ],
  "totals": {"files": 3, "records_parsed": 11, "items_quarantined": 2,
             "duplicate_hints": 1}
}
```

硬不变量：`items_found == records_parsed + items_quarantined`（每文件与总量）。

## ingest_audit.json / ingest_report.md

审计检查 A1–A6（见 ingest_audit.py 头部注释），任一 FAIL 即整体 FAIL，
exit 3，阻断下游环节，直到摄入台账修平。报告供人读，JSON 供机器复核，
两者同源生成、不得手工改写其一。
