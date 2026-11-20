# 语言识别与版本归并规则（version policy）

本文件是 `scripts/langid_version.py` 与 `scripts/reconcile_works.py` 的规范说明；脚本行为与本文件一致，权重/阈值变更通过命令行参数完成并记录在报告 `parameters` 中。

## 1. 总原则

- **文本优先于元数据标签**：正文语种以实际采样文本的统计证据为最终依据；`language`、期刊/出版方等元数据字段只是证据。标签与文本冲突时文本胜出，冲突逐条记录（`conflicts`），并汇总进 `uncertainty`。绝不允许语种标错导致查询词与结果错配。
- **不猜测**：证据不足一律标 `undetermined` 并给出依据；归并证据不足保持分列。宁缺毋滥——错配（把不同论文并成一个 work、把语种标错）比漏并代价更高。
- **可回指**：每条判定携带 locator（file＋JSON 路径/行/row）与采样定位（字段名＋切片偏移＋字符数），复核人可直接回指原始记录。
- **不补造**：归并只组织既有记录，不创造文献、不推断元数据字段。

## 2. 语种判定

### 2.1 采样

- fulltext 字段（fulltext/full_text/body/text/content/pdf_text/extracted_text/plaintext/ocr_text 等，取最长者）长度 ≥ `--min-fulltext`（默认 300）才算有正文；CJK 统一表意、假名、谚文字符按双倍折算（信息密度约为拉丁字符两倍）。
- 长正文按头/中/尾三段各取 4000 字符拼接采样；采样规格（offset/chars）写入 `evidence.sample`。
- 无正文时退而检测摘要（≥80 字符）、再退而检测标题；`basis` 相应标为 fulltext / abstract / title / metadata。

### 2.2 非拉丁文字（文字区间直接定语种，高置信）

| 证据 | 判定 |
|-|-|
| 平/片假名 ≥3 字符且占字母数 >1% | ja（日文必含假名；含汉字+假名仍判 ja） |
| Hangul 占字母数 >10% | ko |
| CJK 占字母数 >20% 且无假名 | zh |
| 西里尔占字母数 >30% | ru |
| 阿拉伯字母占字母数 >30% | ar |

### 2.3 拉丁文字（功能词打分＋特征字符裁决）

- 覆盖 en/pt/es/fr/de/it 六语。对采样文本分词（NFKD 变音折叠＋小写）后统计各语功能词表命中数。
- 最高命中 <3 → `undetermined`（文本太短或非学术散文）。
- 头名与次名命中差 ≤ max(2, 头名×15%) → 特征字符裁决：ã/õ→pt、ñ/¿/¡→es、ä/ö/ü/ß→de、œ→fr、ì/ò→it；裁决有效标中置信，无效标低置信并注明 tentative。
- 否则按命中量与领先幅度标高/中置信。
- 其余拉丁语种（nl/pl/tr 等）不在打分表内：文本会落在"低命中"路径而标 `undetermined`，这是有意的——宁可不判，不可错判。

## 3. 版本类型判定（优先级 R0→R6，先触发先定）

| 规则 | 条件 | 判定 | 置信 |
|-|-|-|-|
| R0 | 与在先记录同指纹（同 DOI，或同标题+首作者+年）且归一化文本哈希一致；或显式 duplicate_of 字段 | exact-duplicate | high |
| R1 | 记录显式 duplicate_of 字段（未被 R0 覆盖时） | exact-duplicate | high |
| R2 | 显式译本关系（translation_of / is_translation_of / relation[].type 含 translat / original_doi / translated_from） | publisher-translation | high |
| R3 | 元数据声明 ≥2 种语言 | bilingual | medium |
| R4a | 无正文，英文摘要，元数据语言非英语 | abstract-only-english；正文语种取元数据语言（basis=metadata，中置信） | high |
| R4b | 无正文，英文摘要，无元数据语言，但标题文本判为非英语 | abstract-only-english；正文语种取标题语种（低置信） | medium |
| R4c | 无正文，英文摘要，无任何正文语种证据 | undetermined | low |
| R4d | 无正文，摘要本身非英语 | original（低置信，仅有摘要佐证） | low |
| R5a | 有正文但语种 undetermined | undetermined | low |
| R5b | 有正文，正文语种与元数据标签冲突且无译本声明 | undetermined（无法区分原文与未声明译本；冲突已记录） | medium |
| R5c | 有正文，无冲突无译本标记 | original | high/medium 随语种置信 |
| R6a | 仅元数据语言可用（metadata-only） | undetermined；正文语种据元数据标低置信、注明 unverified | low |
| R6b | 无文本无元数据 | undetermined | low |

说明：

- 英文摘要＋非英语元数据**不是**标签冲突，而是 abstract-only-english 的定义性模式（R4a/R4b），不记入 conflicts。
- R5b 的 undetermined 是有意的保守：文本证明"这条记录的实际正文是某语"，但没有出版方声明时无法区分"原文即该语"与"未声明的译本"。
- bilingual 需要元数据多语种声明（R3）；正文中夹带英文参考文献列表不构成双语刊证据。

## 4. 跨语种同文归并

### 4.1 候选对生成（blocking）

同 DOI、同 DOI 前缀、同（首作者折叠姓氏＋年）、同（年＋刊名折叠）的记录两两成对；exact-duplicate 对恒为候选。blocking 只决定"哪些对值得打分"，不参与得分。

### 4.2 信号与权重（加性打分，全部写入 merge_decisions）

| 信号 | 权重 | 说明 |
|-|-|-|
| explicit_relation | +1.00 | 显式 translation_of / duplicate_of 指向对方 DOI（含阶段 2 从原始文件补提的 enriched 关系）；决定性 |
| same_doi | +0.90 | 归一化 DOI 完全相同；同一 work，正文语种不同者为不同 version 而非不同 work；决定性 |
| doi_prefix_suffix_relation | +0.35 | 同 DOI 前缀且后缀相似度（SequenceMatcher）≥0.80，如 `...001` vs `...001.en` |
| title_token_jaccard_high / _mid | +0.50 / +0.25 | 变音折叠＋小写后标题 token Jaccard ≥0.80 / ≥0.50；跨语种译名天然低重叠，权重因此受限 |
| numeric_title_tokens | +0.15 | 含数字 token（年份、化学式、型号）Jaccard ≥0.50 且普通标题分未触发；辅助译名对应 |
| first_author_and_surname_set | +0.30 | 首作者折叠姓氏相同且姓氏集合 Jaccard ≥0.60 |
| surname_set_jaccard | +0.20 | 仅姓氏集合 Jaccard ≥0.60 |
| biblio_fingerprint_full | +0.35 | 年、卷、首页全部相等 |
| biblio_year_volume | +0.15 | 年、卷相等 |
| year_equal | +0.05 | 仅年相等 |
| year_gap_penalty | −0.30 | 年份差 >1 |
| volume_conflict_penalty | −0.30 | 卷号冲突（双方都有且不等） |
| first_page_conflict_penalty | −0.30 | 首页冲突 |

### 4.3 决策阈值

- **score ≥ 0.75 → 归并**。含决定性信号（显式关系/同 DOI）置信 high，其余 medium。
- **0.55 ≤ score < 0.75 → 保持分列**：写入 `rejected_candidates`（含全部信号与得分）并汇总进 `uncertainty`。这是"证据不足保持分列"原则的落地。
- score < 0.55 → 忽略。
- 归并按 union-find 成组；每组选 canonical 代表（优先 original 版本、元数据最完整者），但 canonical 仅用于展示，所有版本视图平级保留。

### 4.4 版本视图与去重计数

- work 内按记录生成 version 视图；被标 exact-duplicate 的记录不单独成视图，其 locator 吸收进目标 version（`duplicate_locators_absorbed` 计数），多来源定位全部保留。
- 计数三级对照：`raw_records`（记录级）→ `distinct_versions_after_exact_dedup`（版本级）→ `distinct_works_after_xlang_merge`（work 级）；分语种同时给版本级与 work 级。**一切指标按 work 级统计**；若评审指标误用记录级，多语版本会重复计入、指标虚高，三级对照表使这种虚高可见。
- 孤儿（未与任何记录归并的单记录 work）逐条列出原因：无 DOI、无作者+年 blocking 键、或候选对低于阈值（附 rejected_candidates 指引）。

## 5. 冲突与诚实性

- 语言标签冲突：文本胜出，写入记录级 `conflicts`（含 metadata_language、text_language、resolution、basis）并汇总。
- 原文不可得（abstract-only / metadata-only）：正文语种标推断依据与低置信，`text_availability` 明示；写入 `uncertainty`。
- 原文与译文版本冲突（同 DOI 但书目指纹互斥等）：通过罚分阻止归并，双方各自成 work，情况写入 `uncertainty`。
- result.json 的 `status`：有 undetermined 记录、被拒候选对或解析异常时为 `partial`；阶段 1 报告缺失为 `failed`；其余 `ok`。`change_records` 默认为空数组，仅在运行中对结果做过更正时填写。
