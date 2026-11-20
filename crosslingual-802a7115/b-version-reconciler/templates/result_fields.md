# result.json 字段说明（交付契约）

由 `scripts/reconcile_works.py --case /input/case.json --out /app/output` 组装；同时参考 `/app/work/langid_report.json`（记录级判定明细）与 `/app/work/reconcile_report.json`（归并明细）。

| 字段 | 类型 | 含义 | 完成标准 |
|-|-|-|-|
| case_id | string | 原样取自 case.json | 与输入一致；读不到为 `unknown_case` 且 status≠ok |
| skill | string | `xlang-version-reconciler` | 固定 |
| status | string | ok / partial / failed | 与实际完成情况一致；有 undetermined 记录、被拒候选对或解析异常时为 partial；阶段 1 报告缺失为 failed |
| counts | object | 去重计数对照：`raw_records`（记录级）、`distinct_versions_after_exact_dedup`（版本级）、`distinct_works_after_xlang_merge`（work 级）、`by_body_language`（版本级/work 级分语种对照）、`note`（按 work 计数的警示） | 三级单调不增；指标统计一律取 work 级 |
| works | array | work 组列表。每组：`work_id`、`canonical`（展示用代表元数据）、`n_versions`、`languages`、`version_types`、`versions[]` | 每个 work ≥1 个 version |
| works[].versions[] | array | 版本视图：`version_id`、`record_ids`、`doi`、`title`、`version_type`（original/publisher-translation/abstract-only-english/bilingual/exact-duplicate/undetermined）、`version_confidence`、`body_language`（code/confidence/basis）、`metadata_languages`、`text_availability`（fulltext/abstract-only/metadata-only）、`sources`（locator 列表，file＋pointer）、`duplicate_locators_absorbed`、`conflicts` | 每版本必须带 source 定位与版本类型、正文语种；exact-duplicate 不单独成视图 |
| merge_decisions | array | 每条归并决策：`pair`（record_id 对）、`decision=merged`、`score`、`confidence`、`signals[]`（signal/weight/detail） | 每条可解释、可复算（权重见 rules/version_policy.md §4.2） |
| rejected_candidates | array | 打分落在 [0.55, 0.75) 而**保持分列**的候选对，含信号与理由 | 非空时必须同步出现在 uncertainty |
| orphans | array | 未与任何记录归并的单记录 work：`record_id`、`doi`、`title`、`locator`、`reason` | 每条有可归因的原因 |
| sources | array | 全部解析过的数据文件（来自阶段 1 报告） | 复核人可定位每个文件；解析异常见 parse_notes |
| evidence_records | array | 运行日志逐条 | 时间顺序 |
| uncertainty | array | 缺失、冲突、推断（abstract-only/metadata-only 的语种推断）、被拒候选对、孤儿、output_contract 未覆盖字段 | 如实；无则空数组 |
| change_records | array | 运行中对结果的更正（默认为空） | 有更正才填 |
| output_contract_fields | array | case.json 中 output_contract 的字段名 | 全部镜像，未覆盖字段为 null 并在 uncertainty 说明 |

镜像规则：`output_contract` 中出现的字段若在结果中没有对应内容，置 null 并在 uncertainty 中说明原因；不得删除字段。

记录级（阶段 1）关键字段备查：`body_language.basis`（fulltext/abstract/title/metadata）、`evidence.sampled_field` 与 `evidence.sample.slices`（采样定位）、`evidence.detection.script_counts`（Unicode 区间统计）、`evidence.detection.latin_scores`（功能词得分）、`evidence.decision_rule`（R0–R6 规则编号）、`conflicts`、`fingerprint`、`text_hash`。
