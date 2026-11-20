# 版本谱系链（version_chain）

同一研究可能存在多个版本：预印本（arXiv/bioRxiv 等）与正式发表版（期刊 DOI 记录）。
本规则要求：**合并为一簇，但谱系完整保留，不丢弃任何副本**。

## 1 角色识别（build_canonical.py 的确定性规则）

- `preprint`：有 arXiv id 且无 DOI；或 venue 含 "arxiv"。
- `published`：有 DOI 且不满足 preprint 条件。
- `unknown`：其余（如既无 DOI 也无 arXiv 的导出记录）。

若来源导出本身标注了 preprint/published 类型字段，导入层会保留原值，
角色识别以上述确定性规则为准并在冲突时记入 conflict_log。

## 2 canonical 选择规则

簇内按以下优先级取 canonical（确定性排序，可复算）：
1. 角色：published > unknown > preprint（正式版优先于预印本）；
2. 有 DOI 者优先；
3. 摘要更长者优先；
4. record_id 字典序小者优先（兜底，保证确定性）。

## 3 字段级合并与谱系保留

- 题名/作者/年份/DOI/venue：取 canonical 副本的值；canonical 缺失时按上述
  优先级顺序取第一个有值副本。
- 摘要：取全簇最长者（通常正式版更完整）。
- 每个字段记录 provenance：`{record_id, source_file, source_index}`。
- `version_chain`：`{roles: {record_id: role}, canonical_record_id, copies: [...],
  has_preprint, has_published}`，copies 列出全部非 canonical 副本。
- 筛选只对 canonical 做一次判定，结论经 `propagated_copies` 传播到全部副本
  （final_decisions.jsonl 中每条副本 `inherited_from` canonical_id、
  `via=cluster_lineage`），传播记录可查、可复算。

## 4 原则

- 任何副本都不被删除：identified 计数始终包含全部导入记录，
  审计恒等式 identified = canonical + merged_copies 依赖这一点。
- 年份冲突（预印本 2021 vs 正式版 2022）等字段冲突不是错误，
  全量写入 conflict_log.jsonl 并注明 resolution 规则。
