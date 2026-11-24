# 最小示例运行记录（合成示例）

> 本示例所有输入与输出均为**合成数据**：三个导出文件中的题录系虚构，
> 不对应任何真实文献检索结果，仅用于演示接口与完整流程。

## 输入

| 文件 | 格式 | 内容要点 |
|---|---|---|
| exports/pubmed_export.csv | CSV，UTF-8 | 5 条题录；`ingest-0004` 摘要为空 |
| exports/scopus_export.json | JSON 数组 | 4 个元素；第 3 个是损坏的字符串元素（应隔离）；1 条缺 DOI |
| exports/wos_export.txt | RIS 内容（.txt 后缀） | 4 个块；1 块无 `TI`（应隔离）；1 条标题含 `GÃ¶teborg` 乱码；1 条与 CSV 记录同 DOI |

## 实际执行

```bash
cd <bundle 根目录>
python3 scripts/run_example.py
```

实际输出（2026-11-24，Python 3，macOS arm64）：

```text
PARSED 11 records, QUARANTINED 2 items from 3 files -> .../examples/minimal/output
AUDIT PASS (6 checks) -> .../examples/minimal/output
ingest_audit rc=0 (0=PASS)
```

退出码 0。两次重跑产物逐字节一致。

## 产物目检结论（output/）

- `records_ingested.json`：11 条记录均带 `source_file`/`source_line`；
  `ingest-0004` 标 `missing-abstract`，`ingest-0007` 标 `missing-doi`，
  `ingest-0009`（WoS 第一条）带 `suspected-mojibake-in:title`；
  quarantine 恰为预期 2 条（`json-entry-not-object`、`ris-block-without-title`）；
  duplicate_hints 3 条（DOI×2、标题×1），kept/also 均指向真实 record_id。
- `ingest_ledger.json`：3 个文件条目，每文件 `items_found = parsed + quarantined`。
- `ingest_audit.json`：A1–A6 全 PASS。
- `ingest_report.md`：人读报告，计数与 JSON 一致。

## 负向验证（目检门有效性）

在临时目录中把 `records_ingested.json` 删掉一条记录（模拟台账被篡改）后重跑
`ingest_audit.py`：A2（总量闭合）如预期 FAIL、整体 exit 3；用未被篡改的产物
重跑则恢复 PASS。该操作在临时副本上完成，未改动随包输入与输出。
