# merge_policy.md — 确定性合并策略：字段优先级、冲突消解、缺失语义、排序

本文件是 `scripts/merge_records.py` 的规范文档。合并的每一条 canonical
记录必须做到：**逐字段可回链（field_provenance）、冲突全留痕
（conflict_log.jsonl）、同输入同输出（确定性排序）**。

## 1. 字段优先级表

| 字段 | 优先级（高 → 低） | 规则要点 |
|---|---|---|
| doi / pmid / pmcid | 任一来源提供即收录 | 不按优先级丢弃：所有来源记入 `all_sources`；同簇多个不同值属标识符冲突（见 §3） |
| title | publisher > crossref > europepmc > recordlist > jsonl > csv > unknown | version of record 优先 |
| container / volume / issue / pages | publisher > crossref > europepmc > … | 卷期页以出版商为准，回退 Crossref，再回退 EuropePMC |
| year / pub_date_iso | publisher > crossref > europepmc > … | 日期统一 ISO `YYYY[-MM[-DD]]`，粒度不一致即视为冲突留痕 |
| type | publisher > crossref > europepmc > … | 原样取值，不做类型体系映射 |
| abstract | europepmc > publisher > crossref > … | EuropePMC/出版商摘要通常更完整；crossref 未提供时在 provenance 记 `not_provided_by: [crossref]` |
| authors | crossref > europepmc > publisher > … | Crossref 作者为结构化 family/given，最可靠；统一输出 `[{family, given}]`，跨来源粒度差异（首字母 vs 全名）按优先级取值并记冲突 |

优先级排序确定性：同优先级并列时按 `record_uid` 字典序。

## 2. 字段溯源（field_provenance）

每个字段输出：
```json
"<field>": {
  "value": "选中值", "source": "取值来源",
  "raw_excerpt": "来源文件#item[i] | 原始片段（截断）",
  "all_sources": ["提供过该字段非空值的全部来源"],
  "not_provided_by": ["schema 未提供该字段的来源"],
  "unknown_by": ["提供了字段键但为空/不可解析的来源"]
}
```
`raw_excerpt` 由 normalize_records.py 在抽取时写入，合并阶段只做传递，
保证任何字段值可回链到原始响应的具体 item。

## 3. 冲突消解（conflict_log.jsonl）

触发条件：同一字段在 ≥2 个来源存在**不同非空值**（作者按规范化 JSON
串比较，pages 已做破折号归一）。每条冲突记录：
```json
{"canonical_id": "W001", "cluster_ids": ["C001"], "field": "issue",
 "values_by_source": {"publisher": "3", "crossref": "2"},
 "chosen": {"value": "3", "source": "publisher"},
 "rule": "field_priority", "reason": "多来源值不一致，按优先级取 publisher"}
```
- `rule=field_priority`：普通书目字段冲突，按 §1 优先级取值；
- `rule=identifier_priority`：同簇多个不同 DOI/PMID/PMCID——**不静默**，
  除按优先级取值外，reason 中标注"需人工复核是否误并"，并整体写入
  result.json 的 uncertainty。

## 4. 字段缺失三级语义（聚合级）

单来源单字段语义由 normalize_records.py 记录：`present`（键存在且值可用）/
`unknown`（键存在但为空或不可解析）/ `not_provided`（该条记录 schema 无此键）。
合并聚合规则：

| 聚合 status | 条件 | 示例 |
|---|---|---|
| `present` | 任一来源 present | 正常取值 |
| `unknown` | 无 present，但至少一个来源 unknown | EuropePMC `abstractText: ""` |
| `missing` | 全部来源 not_provided | 仅 Crossref 的记录无 PMID 概念 |

三级语义必须区分写入 canonical 记录的 `field_status` / `identifiers.*.status`
与 provenance 的 `not_provided_by` / `unknown_by`，不得混写、不得编造填补。

## 5. 确定性排序与可重放性

1. 簇内成员按 `record_uid` 字典序；
2. 取值候选按 (来源优先级, record_uid) 排序；
3. canonical 记录按 **(归一 DOI 或 归一题名) 字典序升序**：有 DOI 用
   归一 DOI，无 DOI 用归一题名；完全并列时以首成员 `record_uid` 决胜；
4. `canonical_id`（W001…）与 conflict 的簇定位**在排序之后**分配；
5. 判定日志与冲突日志按 (tier, pair) / 生成序确定性落盘。

因此同一 normalized.jsonl + clusters.json（+ 同一 arbitrations.json）
在任何机器上重跑产出逐字节一致的 merged_records.json（selfcheck A10 断言）。
