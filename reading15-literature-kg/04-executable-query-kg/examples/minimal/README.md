# SYNTHETIC 最小示例（非正式案例结果）

本目录是**合成示例**：两篇论文、全部实体/关系/数值均为演示用虚构内容，
仅用于说明接口与完整流程，**不冒充组织方正式案例结果，也不是预制答案**。

## 内容

- `materials/` — 合成输入：`case.json`（含 output_contract）、`corpus-manifest.json`
  （含真实 sha256）、`material.json`（段落汇总索引）、`primary-material.json`（S1）、
  `secondary-material.json`（S2）。
- `graph.candidate.json` — 候选图谱：12 节点 / 12 边 / 2 条 merge + 3 条 no_merge。
  演示要点：跨篇合并「二氧化钛」「spiro-OMeTAD」；不得合并「样品A vs 样品B」
  （不同物理样品/面积/数值）、「旋涂法 vs 化学气相沉积法」（同对象不同方法）、
  「18.5% 效率 vs 90% 保持率」（不同指标数值，禁止合成一个结论）。
- `queries.json` — 7 条验收查询：node_lookup、带关系/类型过滤的 neighborhood、
  类型化两跳 shortest_path、cross_source（Q4 跨源成立 / Q7 单源诚实为空）、
  merge_decisions，以及 Q5 真实无结果（「钙钛矿量子点」不存在）。
- `output/` — 实际运行产物（带 SYNTHETIC 标签）：graph.json/jsonl、nodes/edges.csv、
  graph.md、graph.svg、manifest.json、validation_report.json、query_results.json、
  query_snapshot.json、result.json。

## 重跑

```bash
python3 ../../scripts/run_all.py \
    --case materials/case.json --input-dir materials \
    --work /tmp/kg04-work --out output \
    --graph graph.candidate.json --queries queries.json --label SYNTHETIC
# 期望：7 条查询 ok=5 empty=2 error=0；status=success
```
