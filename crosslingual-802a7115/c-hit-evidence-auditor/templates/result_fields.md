# result.json 字段说明（交付契约）

ingest 阶段写 `/app/output/result.json`；完整证据台账在 `audit_ledger.json`，统计在 `audit_stats.json`。

| 字段 | 类型 | 含义 | 完成标准 |
|-|-|-|-|
| case_id | string | 原样取自 case.json（经台账传递） | 与输入一致；缺 case 时为 unknown_case 并记 uncertainty |
| skill | string | `xlang-hit-evidence-auditor` | 固定 |
| status | string | ok / partial / failed | ok=复核项零 pending 且校验通过；partial=有 pending 或关键输入降级；failed=台账/队列不可读。必须与实际一致 |
| query_language | string | 查询语种（自报或启发式推断） | 与台账一致 |
| hits | array | 逐命中台账条目（见下） | 每条可凭 locator 回指原文件 |
| risk_distribution | object | `{high, medium, low}` 计数 | 合计 == len(hits) |
| review_stats | object | queued/reviewed/pending/confirmed/false_positive/undetermined/exempt_not_reviewed/validation_warnings | confirmed+false_positive+undetermined+pending+exempt 覆盖全部命中 |
| sources | array | 全部解析过的数据文件＋复核队列文件 | 复核人可定位每个文件 |
| uncertainty | array | 解析失败、概念回退推断、语种不确定、pending、undetermined、契约字段置 null 说明等 | 如实；无则空数组 |
| change_records | array | 运行中对结果的更正（默认空） | 有更正才填 |
| output_contract_fields | array | case.json 中 output_contract 的字段名 | 全部镜像 |

## hits[] 条目字段（证据台账，evidence ledger）

| 字段 | 含义 |
|-|-|
| hit_id | 命中 ID（记录自带或统一补缺 hit-NNNN） |
| title / doi / source / version / record_type | 归因字段：标题、DOI、来源、版本（original/official_translation 等）、记录类型 |
| language / language_detected / language_effective | 语种三列：记录自报、启发式识别、生效值（自报优先）；互不覆盖 |
| locator | `{file, pointer}`：JSON 路径 / CSV 行号 / 文本行区间，可回指 |
| fields_present | 实际参与对齐的字段（title/abstract/body） |
| flags | 命中级标记：secondary_source、translation_record、language_uncertain |
| concept_evidence[] | 逐概念证据：concept_id/label、matched、matched_forms[]（form、form_lang、field、quote、quote_context、span[start,end]、line、locator、abbrev_form/short_form）、matched_langs、expected_langs、wording_mismatch（＋wording_mismatch_detail）、no_surface_match、flags（abbrev_form/short_form/title_only/context_terms_absent） |
| risk / risk_reasons | 风险档与逐条判据（triage 写入） |
| review | 复核结论：queue 条目为 `{queue_id, verdict, back_translation, semantic_consistent, basis, reviewer, reviewed_at}`；免检条目为 `{verdict: "not_reviewed", exempt_reason}`；未复核为 `{verdict: "pending"}` |

## 镜像规则

`output_contract` 中出现的字段：有对应产物的（如 evidence_ledger/audit_ledger/audit_stats）镜像为产物文件路径；无对应内容的置 null 并在 uncertainty 说明原因；不得删除字段。

## 诚实性红线

- verdict 为 confirmed/false_positive 的条目必须能在台账中读到非空 basis（ingest 强制）。
- pending / not_reviewed 不得改写为 confirmed；undetermined 不得计入 confirmed 或假阳性定论。
- 不补造文献与元数据：hits 只来自真实解析出的记录；语种启发式识别与自报分列。
