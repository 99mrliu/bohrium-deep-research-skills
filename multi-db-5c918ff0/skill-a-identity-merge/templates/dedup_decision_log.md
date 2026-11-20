# 去重判定日志（dedup_decisions.jsonl）模板与填写说明

> 本模板对应 dedup.py 的 --decisions 输出。每行一条 JSON 判定，
> 按 (tier, pair, reason_code) 确定性排序；逐条可复算，禁止手工删改，
> 异议请走仲裁或 uncertainty 留痕。

## 行格式

```json
{"pair": ["<record_uid_A>", "<record_uid_B>"],
 "tier": 1,
 "match": true,
 "reason_code": "T1_DOI_EXACT",
 "evidence": {"doi": "10.xxxx/...", "sources": ["crossref", "publisher"]}}
```

| 键 | 取值 | 说明 |
|---|---|---|
| pair | [uidA, uidB]（字典序） | 被判定记录对，uid=来源:文件:item索引 |
| tier | 1 / 2 / 3 | 命中层级，先到先得 |
| match | true / false / arbitrate | 归并 / 拒并 / 送仲裁 |
| reason_code | 见下表 | 机器可读理由码（全集见 references/matching_rules.md §3） |
| evidence | 对象 | 触发值与度量：doi/alias/title_norm/jaccard/author_overlap/year_diff/thresholds |

## 理由码速查

- 归并：`T1_DOI_EXACT` `T1_PMID_EXACT` `T1_PMCID_EXACT` `T1_ID_CROSSREF`
  `T2_TITLE_YEAR_FIRSTAUTHOR`
- 送裁：`T3_FUZZY_ARBITRATE`（绝不自动合并）
- 拒并：`NON_DUP_YEAR_MISMATCH` `NON_DUP_YEAR_UNKNOWN`
  `NON_DUP_AUTHOR_MISMATCH`

## 复核要点（模型）

1. `T1_ID_CROSSREF` 条目的 evidence.alias_source_files 必须非空——
   无来源文件的互链视为臆造，整批作废重查。
2. `NON_DUP_YEAR_MISMATCH` 条目确认不是同一记录的印刷/在线年份差异
   （若是，写入 arbitrations.json 以 merge 覆盖并给 rationale）。
3. 日志不含低相似噪声对；如怀疑漏判，调 `--thresholds` 重跑并记录
   阈值变更到 change_records。
