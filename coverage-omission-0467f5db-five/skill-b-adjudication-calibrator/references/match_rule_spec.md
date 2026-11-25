# 命中判定规则规范（spec_version: 2026.11）

本文件与 `scripts/adjudication_engine.py` 中的 `RULE_SPEC` 常量一一对应；改动任一侧必须同步另一侧并提升 `spec_version`。

## L1 标识符精确匹配

- 规范化：DOI 小写、去 `https://doi.org/` 等前缀、去尾部句点；PMID 去空白。
- 双方都有 DOI：相等 → hit（score 1.0）；不等 → miss 并记 `L1_doi_conflict`（可能的标识符异常，列入漏检归因证据）。
- 仅一方有 DOI 时 DOI 不参与判定，落入 L2；PMID 同理。

## L2 标题+年份近似匹配

- 分词：小写、去标点、去停用词（the/a/an/of/and/in/on/for/to/with/by）。
- 相似度：token 集合 Jaccard。
- 判定：`score ≥ 0.80` 且年份一致（或任一方缺年份）→ hit；`0.65 ≤ score < 0.80` → 灰区 defer_L3；其余 → miss。
- 年份约束开启时，年份冲突直接否决 L2 hit（防止同名不同文）。

## L3 人工裁决队列

- 灰区记录一律进队列，仪器不自动判定；主统计保守计 miss 并附 `conservative_note`，使报告覆盖率为下界估计。
- 人工裁决后回写：把裁决结果追加到标定片段（hit/miss 标签），下一次运行仪器自动吸收为标定证据——这是本仪器持续改进的机制。

## 标定协议

1. 标定片段是带标签的 (ref, candidate) 对，来自既往人工裁决或案例材料。
2. 指标：混淆矩阵（TP/FP/FN/TN/deferred）、precision/recall 及其 Wilson 95% 区间。
3. 阈值扫描 0.60–0.95（步长 0.05）；仅当某阈值 F1 严格高于默认且样本量足够（建议 ≥30 对）才建议调整；建议不自动生效。
4. 片段 <10 对时只报告数字，不给调整建议之外的任何结论性表述。

## 已知边界

- Jaccard token 相似度对长标题的副标题差异敏感；灰区机制用于吸收此类不确定。
- 翻译标题、预印本↔正式版标题差异会压低 score，倾向进入灰区而非误 hit——这是有意的保守设计。
