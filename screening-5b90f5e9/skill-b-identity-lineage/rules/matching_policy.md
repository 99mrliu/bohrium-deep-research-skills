# 三层身份匹配判据（matching_policy）

目标：把「同一研究的副本」正确合并，同时绝不把「不同研究」误并。每个候选对都产出
`{pair, tier, decision(auto_merge/pending/keep_separate), scores, evidence}` 到
`pair_decisions.jsonl`，第三方可按同一批 records.jsonl 独立复算。

## 0 规范化（所有判据的前置）

- DOI：小写；去前缀 `https://doi.org/`、`http://doi.org/`、`https?://dx.doi.org/`、`doi:`；去首尾空白与末尾句点。
- PMID/PMCID/arXiv：去 `pmid:`/`pmc:`/`arxiv:` 前缀，小写。
- 题名：NFKC → 小写 → 非标点保留字符（`[^0-9a-z一-鿿]`）替换为空 → 压缩空白。
- 首作者姓：首作者串含逗号取逗号前，否则取最后一个空白分词；NFKC+小写+去非字母。
- 年份：取首个 4 位 `(19|20)\d{2}`。

## 1 阻塞（只为控制候选对规模，不做判定）

桶：归一题名前 40 字符 / 归一 DOI / PMID / arXiv / 年份。同桶两两成候选对。
注意：阻塞只决定「评估哪些对」，不决定合并；年份桶会产生大量
keep_separate 对，这些是「不合并」的显式证据而非噪声。

## 2 三层判据

| 层 | 判据 | 决定 | 证据要求 |
|---|---|---|---|
| Tier1 | 归一 DOI 相同，或 PMID 相同，或 arXiv id 相同（双方均非空） | auto_merge | 标识符类型 + 归一后的值 |
| Tier2 | 归一题名完全相同（非空）且年份差 = 0 | auto_merge | norm_title + year |
| Tier3 | 题名 token 集合 Jaccard ≥ 0.6 且首作者姓相同且年份差 ≤ 1 | **pending（只进仲裁队列，绝不自动合并）** | 三项分数 + 双方关键字段对照 |
| 其余 | — | keep_separate | 未满足判据的分数记录 |

跨标识符禁令：PMID-only × DOI-only 的记录对不得臆造标识符映射，
只能凭 Tier2/Tier3 书目证据（题名/作者/年份）判断。

## 3 两类错误的防护

- **漏并（该并没并）**：Tier2 捕获题名细微差异（标点/大小写/破折号）；
  Tier3 捕获年份差 1 的预印本×正式版等；Tier3 候选对**必须全部裁决**，
  `apply_arbitration.py` 对漏裁的 pending 对 exit 3，不允许静默跳过。
- **误并（不同研究被并）**：Tier3 绝不自动合并；标题相似但人群/年份/期刊/DOI
  冲突的对，模型必须显式判 split；split 也写入 `split_decisions` 留痕
  （含 rationale 与 scores），与 merge 一样可复算。`conflict_log.jsonl`
  记录簇内字段值冲突，是事后发现误并的审计线索。

## 4 Tier3 仲裁指引（模型职责）

对每个 pending 对，比较 review_queue.json 中 a/b 双方的
title/year/first_author/doi/pmid/arxiv/venue：
- 判 merge：需要能指出「同一研究」的实质依据（如题名一致且为预印本×正式版、
  数据与结论描述一致），rationale 非空。
- 判 split：需要能指出「不同研究」的实质依据（如人群、数据规模、方法、
  DOI、期刊冲突），rationale 非空。
- 拿不准时倾向 split 并在 rationale 写明不确定点（误并的代价高于漏并：
  漏并只多筛一条，误并会让一项研究凭空消失且结论被错误继承）。
