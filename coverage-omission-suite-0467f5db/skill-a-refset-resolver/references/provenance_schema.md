# reference_set.json 逐字段出处模式（schema v1.0.0）

本模式定义冻结参考集文件 `reference_set.json` 的顶层结构与每条记录的字段含义。每条记录都必须能被追溯到材料文件中的具体位置；缺少出处指针的记录视为校验失败（退出码 3）。

## 顶层字段

| 字段 | 类型 | 含义 |
|---|---|---|
| schema_version | string | 参考集模式版本，冻结版为 "1.0.0"。结构变更须升版本。 |
| case_id | string | 与 case.json 一致。 |
| frozen_at | string(ISO8601) | 冻结时间（UTC）。 |
| frozen_by | string | 冻结脚本名（refset_build.py）。 |
| denominator_policy | string | 分母来源政策声明：仅来自本地参考材料，与检索结果无关。 |
| records | array | 参考集条目，见下表。 |
| stats | object | total、usable、verified、needs_manual_review、excluded、merged_away 六元统计。 |
| status | string | complete / partial / failed，反映构建环节最弱状态。 |
| limitations | array[string] | 构建期间的诚实降级说明。 |

## 记录级字段

| 字段 | 类型 | 含义与出处要求 |
|---|---|---|
| ref_id | string | 稳定编号，格式 `REF-NNNN`，按年份、标题排序分配；冻结后不得复用。 |
| title | string | 文献题名；核验命中时以本地权威响应为准补齐。 |
| authors | string | 作者串；缺省为空串，不得臆造。 |
| year | string(4位) | 出版年；缺省为空串。 |
| journal | string | 刊名；核验命中时补齐。 |
| doi / pmid / pmcid / arxiv | string\|null | 规范化后的标识符；规范化规则见 identifier_normalization_rules.md。 |
| verification_status | string | verified（本地或联网兜底核验一致）、unverified（无任何命中）、identifier_conflict（多标识符指向不同文献）。 |
| verification_source | string\|null | local_response（本地留存响应文件命中）或 live_api_cached（urllib 兜底命中，响应已缓存）。 |
| verification_evidence | array | 命中证据：via（命中字段）、id、channel，以及 slim 后的 entry（file、json_ptr、title、journal、year 等）。 |
| inclusion_reason | string | 纳入理由，如 `parsed_from:bibtex`；须能说明"为什么这条记录属于分母"。 |
| source | array[string] | 出处指针列表，格式 `材料相对路径#位置`（CSV 为行号 `#L12`，JSON 为索引 `#[3]`，PDF 提取文本为 `#pdfL45`）；合并记录保留全部出处。 |
| merged_from | array[string] | 被本记录合并掉的其他出处指针（仅合并胜者携带）。 |
| disposition | string | include、exclude_retracted、needs_manual_review 等，规则见 failure_taxonomy.md。 |
| flags | array[string] | 异常标记，如 no_fulltext_url、identifier_conflict、no_identifier。 |
| usable | bool | 是否计入可用分母；exclude_retracted 为 false。 |
| usable_for_fulltext | bool | 全文是否可得；不影响题录级 usable。 |

## 配套台账

- `dedup_log.json`：每次合并一条记录，含 action（merge_identifier / merge_title_similarity）、dropped_source、kept_source、similarity 或 shared_key、note。禁止静默合并。
- `exclusion_log.json`：每条非 include 处置一条，含 source、title 摘录、disposition、flags、reason。
- `result.json` 的 change_log：冻结之后的任何变动（含人工修订、降级事件）逐条记录，格式为 time / actor / change / reason。

## 冻结语义

冻结意味着：分母数值与逐条记录在覆盖测量期间不可变更。若发现参考集错误，正确做法是升版本号（如 v1.0.1）、写入 change_log 说明原因，再以其为新分母重新测量覆盖率；禁止就地修改 v1.0.0 的分母数值而不留痕。
