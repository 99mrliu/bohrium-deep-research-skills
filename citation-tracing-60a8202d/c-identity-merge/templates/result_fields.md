# result.json 字段说明（交付契约）

| 字段 | 含义 | 完成标准 |
|-|-|-|
| case_id | 原样取自 case.json | 与输入一致 |
| skill | `crossdb-identity-merge` | 固定 |
| status | ok / partial / failed | 无记录时 partial 且说明 |
| parameters | review_threshold | 与运行一致 |
| clean_works | 去重后的簇清单：cluster_id、canonical（含 rid/doi/arxiv/title/year/authors/venue/version/ext_ids/locator）、version、versions_present、all_doi、all_arxiv、all_ext_ids、members（含定位）、field_conflicts | 每条摄入记录恰好属于一簇；簇间硬标识唯一 |
| review_queue | 待人工裁定对：pair、a/b 摘要、score、evidence（含原因） | 未自动合并；逐条可回指 |
| conflicts | 簇内字段冲突汇总 | 与 clean_works 内 field_conflicts 一致 |
| stats | records_ingested / clusters / multi_record_clusters / duplicates_removed / review_pairs / pairs_checked / corpus_files | 算术自洽：removed = ingested − clusters |
| sources | 解析过的文件 | 可定位 |
| evidence_records | 运行日志 | 时间顺序 |
| uncertainty | 待审说明、残记录、解析异常 | 如实 |
| change_records | 更正（默认空） | 有更正才填 |
| output_contract_fields | output_contract 镜像字段名 | 未覆盖字段为 null 且不得删除 |

配套文件：`merge_ledger.json`（逐簇合并证据）、`merge_table.md`（人读表）。
