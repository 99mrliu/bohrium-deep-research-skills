# query_cookbook — 预置查询手册

`graph_query.py` 提供 9 个预置查询，输出 `query_report.json`（机器读）
与 `query_report.md`（人读）。可用 `--only <名称>` 单跑某一个查询。
所有查询都是图结构的确定函数：同图必得同报告。

## 查询定义

### 1. q_orphan_claims — 无证据论断（孤儿）
- **定义**：无任何 supports 边且未标诚实的 Claim 列表。
- **输出**：`[{claim, task, text}]`。
- **用法**：交付前必须为空（或全部改诚实标记），否则门禁拦截。

### 2. q_coverage_matrix — 证据覆盖矩阵（Task × Anchor）
- **定义**：每个 Task 经 pass 证据链（Task←Claim←Evidence→Anchor）
  落到各锚点的证据计数。
- **输出**：`{task: {anchor: count}}`，md 渲染为表格。
- **用法**：一眼看出哪题证据单薄、哪段源文支撑了哪题。

### 3. q_reused_evidence — 被多任务复用的证据
- **定义**：被 ≥2 个 Task 的 pass 证据引用的锚点。
- **输出**：`[{anchor, tasks}]`。
- **用法**：识别"高强度依赖段落"——该锚点若被误读，多题同错。

### 4. q_conflict_list — 冲突清单
- **定义**：图中全部 ConflictEdge（numeric_mismatch / negation）。
- **输出**：`[{id, kind, node_a, node_b, attr, unit, values, detail}]`。
- **用法**：冲突是显式边；凡涉及冲突锚点的题目，答案必须并列报告
  并注明分歧，不得擅自二选一。

### 5. q_evidence_chain — 某 Task 的完整证据链
- **定义**：对每个 Task 列出 Claim → Evidence(quote, verdict,
  reason) → Anchor 全链。
- **输出**：`{task: {label, claims: [{id, text, honest, evidence:
  [{id, anchor, verdict, reason, quote}]}]}}`。
- **用法**：逐题复核"结论是否查得回源文锚点"。

### 6. q_uncited_anchors — 未引用锚点（源文覆盖盲区）
- **定义**：没有任何 pass 证据 derived_from 的锚点。
- **输出**：`[{anchor, kind, preview}]`。
- **用法**：盲区提示——若某题理应引用盲区锚点，说明阅读遗漏；
  若盲区确为无关段落，可安全忽略。

### 7. q_score_derivation — 逐题 0/1/2 分数推导
- **定义**（图指标的确定函数，诚实标记 claim 不参与）：
  - `2`：全部参评 claim 均有 ≥1 条 pass 支持且无 fail 边；
  - `1`：至少一条 pass 证据，但存在 fail 边或未获支持的 claim；
  - `0`：无任何 pass 证据；
  - `null`：仅含诚实标记 claim 或无论断（不可评分）。
- **输出**：`{task: {score, rationale, claims_graded, pass_claims,
  fail_edges}}`。
- **用法**：score 不取代人工评分，只给出可复算的下界估计与理由。

### 8. q_honest_flags — 诚实标记清单
- **定义**：全部 `honest=true` 的 Claim 及其理由。
- **输出**：`[{claim, task, text, reason}]`。
- **用法**：核对诚实标记是否被滥用（把答不出的题全标记掉会被
  覆盖率与分数推导暴露）。

### 9. q_metrics — 图谱汇总指标
- **定义**：节点/边分类计数、锚点覆盖率（cited/total）、孤儿数、
  fail 数、degraded 数、冲突数。
- **输出**：见 `query_report.json.metrics`。
- **用法**：交付前自查"图谱非退化"（有节点、有边、覆盖率 > 0）。

## 典型用法：reviewer 如何用查询复核一个分数

以复核 q3 得 2 分为例：

1. 跑 `graph_query.py --only q_score_derivation`，看
   `q3.rationale` 是否命中"全部论断有 pass 支持且无 fail 边"。
2. 跑 `--only q_evidence_chain`，沿 q3 的每条 Evidence 检查：
   verdict 是否 pass、quote 是否逐字落在 anchor 原文内
   （可对照 graph_map.md 中的锚点文本）。
3. 跑 `--only q_conflict_list`，确认 q3 涉及的锚点是否出现在任何
   ConflictEdge 中；若是，检查最终答案是否并列报告了双方数值。
4. 跑 `--only q_orphan_claims` 与 `--only q_honest_flags`，确认
   该分数不是靠藏起无证据论断或滥用诚实标记换来的。
5. 四步全部通过，分数方可采信；任何一步存疑，回到
   `failure_analysis.md` 定位题目 ID、摘录与修法。
