# result.json 字段模板

终版 `/app/output/result.json` 的字段约定（build_result.py 生成）：

| 字段 | 类型 | 说明 |
|---|---|---|
| case_id | string | 防御式取自 case_id/id/caseId，缺省 `unknown_case` |
| status | string | `in_progress`（部分版）→ `completed` / `partial_failure` |
| skill | string | 固定 `stat-recheck-evidence-auditor` |
| output_contract | object/array | **case.json 中 output_contract 的原样镜像**，不增删字段 |
| contract_fields | object | 契约字段名 → 填充值；脚本无法填的置 null 并记 uncertainty |
| statistics_grade | object | {grade, limited, counts, per_doc_rows, derivation[], thresholds_ref} |
| verification_summary | object | {total_rows, verified_rows, failed_rows} |
| sources | array | 每篇 {doc_id, source_path, source_sha256, abstract_only, status} |
| documents | array | 同 docs.jsonl（抽取阶段写入） |
| recheck_rows_path | string | work 目录中复核行位置 |
| semantic_queue_pending | int | 未裁决的 needs_semantic 条数 |
| uncertainties | array[string] | 全部不确定性与降级原因，诚实记录 |
| change_log | array[object] | {event, at, ...} 变更记录 |
| task_source | string/null | "task.md" 或 null |
| updated_at | string | UTC 时间戳 |

契约字段自动填充映射（build_result.py 中 CONTRACT_FILLERS）：

- 字段名含 grade/quality/rating/level → 等级
- 含 limited → limited 标志
- 含 finding/check/result/discrepanc/count/statistic → 计数汇总
- 含 audit/trail/reproduc → "audit_trail.md"
- 含 report/summary/markdown → "recheck_report.md"
- 含 verif/quote/anchor/evidence → 校验摘要

未命中映射的字段保持 null，**绝不编造内容**，并在 uncertainties 中说明
"需模型/人工补充"。
