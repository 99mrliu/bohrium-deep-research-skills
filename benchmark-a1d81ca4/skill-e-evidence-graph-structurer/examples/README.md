# 合成示例（SYNTHETIC EXAMPLE）

本目录为**合成示例**：`source_excerpt.txt` 中的两段"文献摘录"与汇总表均
为编造素材，刻意让汇总表的过电位（312 mV）与摘录 A（287 mV）对同一量
给出不同数值，用于演示 `numeric_mismatch` 冲突检出。本示例不包含任何
隐藏案例的预制答案。

## 运行

```bash
bash run_example.sh /tmp/a1d81ca4-e-demo-out   # 参数为输出目录，默认 ./out
```

## 流程

1. `graph_init --init-result`：建图并先写合法部分 `result.json`。
2. `graph_link`（`agent_answers.json`）：故意包含
   - 一条**无证据论断**（循环稳定性）→ 演示孤儿检出；
   - 一条**错锚点证据**（引文不在 doc1.para1 内）→ 演示 fail 边。
3. 修复版 `agent_answers_fixed.json`（孤儿改诚实标记、错锚点改写为
   原文可查表述）重新 init + link，孤儿清零。
4. `graph_query`：全部 9 个预置查询。
5. `graph_export`：导出交付物。

## 预期产物

- `out/work/graph.json`、`link_report_raw.json`、`link_report_fixed.json`、
  `query_report.json`、`query_report.md`、`result_fields.json`
- `out/evidence_graph.json`、`graph_map.md`、`failure_analysis.md`、
  `result.json`

## 预期图谱指标（修复后）

| 指标 | 预期值 |
|---|---|
| Source / Anchor / Task | 1 / 4 / 3 |
| Claim（修复后） | 5（其中诚实标记 1） |
| Evidence / verdict | 5 条全部 pass，fail=0，degraded=0 |
| 孤儿 | 修复前 1 → 修复后 0 |
| ConflictEdge | 1 条 `numeric_mismatch`：doc1.para1(287 mV) ↔ doc1.para4(312 mV)，属性"过电位" |
| 锚点覆盖率 | 3/4 = 0.75（doc1.para3 为未引用锚点/覆盖盲区） |
| 多任务复用 | doc1.para1 被 q1、q3 复用 |
| 逐题分数 | q1=2，q2=2，q3=2 |
| result.json status | 成功 |

确定性：重复运行 `graph_init`，`graph.json` 的 sha256 逐字节一致。
