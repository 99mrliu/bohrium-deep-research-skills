# 记录级异常分类与处置规则（failure taxonomy）

本文件定义参考集治理中出现的全部记录级异常类型、判定证据与处置动作。处置动作取值：include、exclude_retracted、needs_manual_review、flag_keep_no_fulltext。所有非 include 处置必须写入 exclusion_log.json 并给出 reason。

## 分类总表

| 编号 | 异常 | 判定证据 | disposition | usable |
|---|---|---|---|---|
| F1 | 撤稿 | 本地响应含撤稿标记（见下） | exclude_retracted | false |
| F2 | 重复记录 | 标识符相同，或标题 Jaccard ≥ 0.85 | 合并入胜出记录（dedup_log 留痕） | 以胜者为准 |
| F3 | 全文不可得 | fullTextUrlList 为空或仅有付费墙条目 | flag_keep_no_fulltext | true（usable_for_fulltext=false） |
| F4 | 标识符冲突 | 同记录多标识符命中不同题名（Jaccard < 0.6） | needs_manual_review | true |
| F5 | 标识符不可解析 | 给出 DOI/PMID 但本地与联网兜底均无命中 | needs_manual_review | true |
| F6 | 无任何标识符 | 题录仅有标题等字段 | needs_manual_review（flags=no_identifier） | true |
| F7 | 解析低置信 | 来自 PDF 启发式解析（编号行启发式） | needs_manual_review（flags=low_confidence_parse） | true |

## F1 撤稿判定证据（按可信度排序）

1. Crossref 响应 `message.relation` 中存在 update 关系且类型含 "retraction"。
2. EuropePMC 响应期刊字段（journalInfo.journal.title）含 "Retraction"。
3. 响应正文含 `"retracted": true` 或题录题名以 "Retraction of" 开头。

仅证据 3 命中时，若撤稿标记仅来自单一渠道，处置仍为 exclude_retracted，但须在 uncertainty 中注明单一渠道。

## F2 重复合并细则

- 强键：规范化 DOI、PMID、PMCID、arXiv 中任意一者相同即视为同一文献；通过传递闭包聚簇。
- 弱键：无标识符条目与已有代表记录的标题键 Jaccard ≥ 0.85。
- 胜出规则：字段完整度优先（有 DOI/PMID、年、刊者胜）；并列时取解析来源更结构化者（BibTeX/RIS 优先于 PDF 启发式）。
- 胜者继承败者的全部 source 指针；dedup_log 逐条记录，禁止静默丢弃。

## F3 全文不可得细则

- 判定依据仅限本地响应中的 `fullTextUrlList` 等结构化字段；不得依据文件名或猜测。
- 题录级核验不因无全文而失效：该记录仍是分母成员。

## F4 标识符冲突取舍

- 以字段更全、来源更权威的响应记录为展示基准（本地响应优先于联网兜底）。
- 取舍依据写入 verification_evidence 与 uncertainty，便于复核。

## F5 与 F6 的关系

- F5 要求记录至少携带一个规范化后的标识符；F6 要求一个也没有。
- 二者共存时按 F4 → F5 → F6 的顺序判定，flags 可叠加。

## 超时与离线

- 联网兜底请求超时即视为该记录无联网命中（归入 F5 或保持 unverified），在 limitations 中记录失败请求与时间点；禁止无限重试。
- 指定 `--no-live` 时全部联网判定跳过，F5 的 flags 记为 identifier_unresolvable_offline。

## 与覆盖测量的衔接

被 exclude_retracted 的记录不进入可用分母统计，但仍在 reference_set.json 中保留并标注 disposition；覆盖测量以冻结参考集全部记录为分母，同时在报告中区分 usable 子集，避免"排掉难找的记录抬高覆盖率"的失真。
