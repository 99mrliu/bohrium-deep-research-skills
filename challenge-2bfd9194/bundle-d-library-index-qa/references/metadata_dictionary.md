# 元数据字段字典

## LIBRARY_MANIFEST.jsonl（每来源文件一行，含跳过项；行数 = 输入文件数）

| 字段 | 类型 | 含义 |
|---|---|---|
| source_path | str | 相对 /input 的源路径（NFC 规范化） |
| rel_path | str\|null | 相对 library/ 的落库路径；跳过项为 null；别名指向规范副本 |
| sha256 | str\|null | 内容 SHA-256（64KB 流式）；不可读为 null |
| size | int\|null | 字节数 |
| mtime | str\|null | ISO8601 UTC |
| category | str\|null | papers / data / scans / supplementary / drafts / admin / _unassigned |
| action | str | commit_new（落库，含幂等重跑）/ already_committed_identical（别名）/ skipped |
| duplicate_of | str\|null | 别名的规范副本 source_path |
| title_guess | str | 首非空行（≤60 字符），二进制为文件名主干；**不是**猜作者/年份 |
| reason | str | 跳过或幂等原因 |

## catalog.db

### files 表（行数恒等于 manifest 行数）

`source_path, rel_path, sha256, size, category, mtime, title_guess, text_status, action, duplicate_of`

text_status 枚举：`indexed` / `indexed_truncated`（>2MB 截断）/ `not_indexed_binary` / `alias_of_indexed`（别名，内容同规范副本）/ `missing_on_disk` / `skipped`。

### fts 表

FTS5 虚表 `fts(path, content)`，content 为 CJK bigram 展开后的全文；sqlite 无 FTS5 时降级为普通表（index_stats.json 记 degraded:true）。

### docs 表

`docs(path PRIMARY KEY, content)`：已索引文本文件的**原文**，snippet 的来源与逐字核对依据。

## index/index_stats.json

`manifest_rows, files_table_rows, unique_library_files, indexed_text_files, not_indexed_binary, skipped_rows, truncated_files, by_category{}, by_text_status{}, index_coverage（=indexed_text_files/unique_library_files，二进制不计入分子）, degraded, degrade_reason, db_path`。

## QA_LOG.json（JSONL）

见 references/query_syntax.md。status ∈ answered / partially_answered / unanswered；confidence ∈ high / medium / low。

## REBUILD_DIFF.json

`status`（empty_diff / non_empty_diff）、`runtime_entries / rebuilt_entries`、`missing_in_rebuild[] / extra_in_rebuild[]`（{rel_path, sha256, size}）、`rebuild_degraded`。

## audit_report.json

`overall`（PASS/FAIL）+ checks[]：deliverables_present、files_rows_eq_manifest、input_coverage、hash_spot_check（20% 至少 5 条）、qa_evidence_real（逐条全查）、rebuild_diff_empty；每项 {check, status, detail}。

## result.json

`case_id, status（in_progress/complete/partial/blocked）, contract_fields{}（output_contract 镜像：字段名→交付物相对路径，映射不了给 {value:null, reason}）, summary, qa_summary, degraded, sources, uncertainties, change_records, failures_and_recovery, updated_at`。
