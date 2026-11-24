# 证据 schema 与违规码总表

本文件是 build_corpus.py 之外三个校验脚本的输入格式与全部违规码的唯一权威定义。

## 1. 检索/筛查日志（retrieval_log.py）

每行一个 JSON 对象（.jsonl）：

```json
{"query_id": "q1",
 "query_string": "scope=provided-corpus: all 15 records in ./materials",
 "source": "provided-corpus",
 "date": "2026-01-15",
 "hits": 15, "kept": 12,
 "excluded": [{"record_ref": "L011", "reason": "video-only; out of scope"}]}
```

- `hits`：该查询命中条数；`kept`：保留条数；`excluded`：被排除条目的数组。
- **闭合纪律**：`hits == kept + len(excluded)`。
- 语料由平台给定时，用 `source:"provided-corpus"` 的伪查询行记录范围——
  诚实说明"检索"在此处的含义。
- `record_ref` 不在 canon 中时列为外部引用（external_refs），**允许但标记**。

产出 `retrieval_report.json`：`{queries, total_hits, closure_violations,
other_violations, external_refs}`。有致命违规 exit 1。

违规码：

| code | 致命 | 含义 |
|---|---|---|
| `closure_violation` | 是 | hits != kept + len(excluded) |
| `empty_exclusion_reason` | 是 | 排除条目缺非空 reason |
| `malformed_line` | 是 | 行非合法 JSON / hits、kept 非非负整数 / excluded 非数组 |
| （external_refs 条目） | 否 | record_ref 不在 canon（`not_in_canon_external`）或 canon 缺失（`canon_missing_cannot_resolve`） |

## 2. 空白声明（gap_tribunal.py）

```json
{"gap_id": "gap-1",
 "statement": "No method in the provided corpus targets ... for underwater ...",
 "gap_type": "missing-population-or-setting",
 "exclusion_evidence": {
   "scope_description": "Provided corpus of 15 records (2015-2024), screened via q1, q2; no external search executed.",
   "query_ids": ["q1", "q2"],
   "near_misses": [{"record_id": "L014", "why_not": "..."}]}}
```

- `gap_type` ∈ {repeated-unsolved-question, method-failure-on-object-or-scale,
  conflict-unresolved, missing-population-or-setting}（定义见 gap_taxonomy.md）。
- `query_ids` 必须存在于 retrieval_report（先跑 retrieval_log.py，或用
  `--report FILE` 指定报告）。
- **近失重叠规则（健全性地板，不是语义判断）**：
  - token = 小写 [a-z0-9]+ 且长度 ≥3 的词（去内置停用词）∪ 单个 CJK 字；
  - 记录 token 取自 title + abstract + keywords；无词干化（method ≠ methods）；
  - 近失通过当且仅当 Jaccard(statement, record) ≥ 0.08 **或** 共享 token ≥ 2。
  - 设计意图：拦住"随手挂一条毫不相关的记录充数"；误杀时在 why_not 中补充
    与声明共用的关键词重跑，并在 uncertainty 注明人工复核。

产出 `gap_verdicts.json`：`{gaps: [{gap_id, verdict: admissible|rejected,
violations[], evidence_summary}]}`。任一 gap rejected 则 exit 1。

违规码：

| code | 含义 |
|---|---|
| `bare_gap_claim` | exclusion_evidence 缺失或全空（"没检索到即空白"） |
| `missing_scope` | 有 exclusion_evidence 但 scope_description 为空 |
| `no_near_misses` | near_misses 为空 |
| `unknown_query` | query_id 不在 retrieval_report 中（含报告缺失时） |
| `irrelevant_near_miss` | 近失 record_id 不在 canon，或主题重叠低于地板 |
| `empty_why_not` | 近失缺非空 why_not |
| `unknown_gap_type` | gap_type 不在四分类中 |

## 3. 冲突条目（conflict_pairs.py）

```json
{"conflict_id": "c1",
 "quantity_or_claim": "Effect of X on Y mAP@0.5 on ExDark",
 "side_a": {"record_ids": ["L009"], "value_or_finding": "mAP improves by +4.2 points",
            "location": "L009 abstract; Table 2"},
 "side_b": {"record_ids": ["L010"], "value_or_finding": "mAP changes by -0.3 points; n.s.",
            "location": "L010 abstract; Section 4"},
 "status": "unresolved"}
```

- 双侧必须各有 ≥1 个 canon 内 record_id、非空 value_or_finding、非空 location。
- 两侧数值归一化（小写、压缩空白、去收尾引号与 .。;；）后**相同**则判
  `not_a_conflict`——数值相同不构成冲突。
- 指标/设置不同导致不可直接比较时：`status = "unresolvable-without-harmonization"`，
  如实记录两侧原文数值。
- 材料确无位置信息时 location 写 `"location unavailable in provided material"`。

产出 `conflict_report.json`：`{conflicts: [{conflict_id, verdict, violations[],
sides_summary}]}`。任一 rejected 则 exit 1。

违规码：

| code | 含义 |
|---|---|
| `missing_side` | side_a / side_b 缺失或不是对象 |
| `no_record_ids` | 某侧 record_ids 为空 |
| `unknown_record` | record_id 不在 canon |
| `empty_value` | value_or_finding 为空 |
| `not_a_conflict` | 两侧归一化数值相同 |
| `missing_location` | location 为空 |
