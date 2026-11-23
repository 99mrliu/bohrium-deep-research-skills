# 查询 DSL（确定性执行）

查询由 `scripts/query_run.py` 在 `graph.jsonl` 上**确定性**执行：
同一份图谱 + 同一份查询规格 ⇒ 同一份输出。每个结果都是**结果子图**
（nodes + edges + evidence 逐字短引），不是自由文本回答。

## 查询类型

### compare —— 条件化比较

```json
{"query_id": "q1", "type": "compare",
 "question": "在 LowMT-100 / BLEU / low-resource 条件下谁优于 TransB？",
 "params": {"dataset": "n_lowmt", "metric": "n_bleu", "condition": "n_lowres"}}
```

返回该条件作用域内全部 `outperforms`/`compares_with` 边；
输出固定带 `"no_global_winner": true`，并列出卷入冲突的边 id。
比较结论只在查询给定的作用域内成立。

### measurements —— 测量清单

```json
{"query_id": "q2", "type": "measurements",
 "params": {"node": "n_transB", "dataset": "n_lowmt", "metric": "n_bleu"}}
```

返回该节点的全部测量边（含冲突标记）。两个来源数值不同时，
结果同时列出双方并带 `conflict_flags`，不选赢家。

### direct_relation —— 直接关系判定

```json
{"query_id": "q3", "type": "direct_relation",
 "params": {"subject": "n_transA", "object": "n_distilT"}}
```

- 有直接边 → `answer: "direct_relation_exists"` + 子图；
- 无直接边但存在共现记录 → `answer: "no_direct_relation"` +
  `cooccurrence_notes`，明确“共现≠直接关系”，**不补边**。

### neighbors —— 一跳邻居

```json
{"query_id": "q4", "type": "neighbors", "params": {"node": "n_transB"}}
```

## 运行方式

```bash
python3 scripts/query_run.py \
  --graph  /app/output/graph.jsonl \
  --queries /app/work/queries_spec.json \
  --out /app/output/queries.json
```

正式案例要求**至少 3 个真实执行的查询**；查询必须覆盖：
至少一个条件化比较/测量查询，至少一个能展示冲突或
“无直接关系”诚实回答的查询。
