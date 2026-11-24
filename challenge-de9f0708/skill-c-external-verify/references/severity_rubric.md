# Finding 类型 × 严重度规则表（severity rubric）

所有 finding 统一要素：`id`、`type`、`severity`(critical/major/minor/info)、
`location`{file,page,section,quote 逐字}、`evidence`、`suggestion`、
`verdict_status`(确认/待复核+理由)；类别归属 fact_error / insufficient_evidence /
norm_issue / suggestion 四选一。

## 类型 × 严重度 × 证据要求

| type | 默认 severity | 类别 | 升级/降级条件 | 证据要求 |
|---|---|---|---|---|
| fabrication_suspected | critical | fact_error | 不可降级为确认；必须 `待人工终裁` | **两信号齐备**：Crossref 无结果（404/相似度<0.80）**且** doi.org 解析 4xx；附 query_log 原文。单一信号 → 不立项，仅 `pending_review` |
| metadata_mismatch | major（title/year/authors 不符）；minor（仅卷期页/容器名不符） | fact_error | 预印本版本差异、跨年见刊 → 降级 info 或撤项 | Crossref 检索记录原文与文献著录逐字段对照（retrieved_records） |
| claim_citation_mismatch | major | insufficient_evidence | 语境句与文献通读后确认相关 → 撤项；确认无关且支撑关键论断 → 升 critical | 引文标记语境句逐字 + 文献标题/摘要主题对照；本地零重叠仅为 low-confidence 候选 |
| duplicate_reference | major | norm_issue | 仅标题相似、作者/年份/期刊不同（撞题综述）→ 撤项 | 两条目 raw 原文 + 标题归一化相似度 + 人工核对结论 |
| missing_field | minor（缺单字段）；major（[n] 指向不存在条目） | norm_issue | 抽取失败导致 → 人工补录后撤项 | 字段空缺清单 + 原文摘录 |
| format_inconsistency | minor | norm_issue | 全文仅个别处 → info | 体例混用实例（编号 vs 作者-年份）各至少一例逐字 |
| suggestion | info | suggestion | — | 可执行改进建议，不得伪装成问题 |

## 证据强度纪律

1. `确认` 只能用于：本地可机械复核的事实（年份 > 当前年、DOI 形态非法、字段为空）
   或有检索记录原文支撑的外部判定（match / mismatch）。
2. `待复核` 必须写明理由与复核路径（"需联网查 Crossref 记录"/"需人工通读语境"）。
3. 误报代价 ≥ 漏报代价：拿不准的类型归属一律降一级 severity 并标 `待复核`。
4. 每条 finding 的 `evidence` 必须能指回：本地规则名（lint rule）或外部来源
   （URL + 检索到的原文），两者都没有的 finding 不得出现在最终报告中。
