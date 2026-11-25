# SYNTHETIC example, not real papers

# 任务简报（合成示例）

围绕两篇**合成的**钙钛矿太阳能电池小论文构建知识图谱并交付可审查的产物集合：

1. 从两段全文（primary S1、secondary S2）中抽取实体与关系，所有节点/边必须携带
   `source_id` + `paragraph_id` + 逐字引文（该段落文字的精确子串）。
2. 遵守合并纪律：跨篇别名合并需给出归一化键与理由；同名不同物（两篇中的 "TiO2"）
   必须显式记录为 NON-merge；不同条件下的数值冲突（21.1% 初始 vs 18.7% 湿热老化后）
   必须保留为两条独立 claim。
3. 执行 `case.json` 中的 3 个 `query_specs`，每个查询给出结果子图、证据与明确列出的
   未知/未报告项（如滞后指数 hysteresis index 未报告）。
4. 交付：`result.json`（镜像 output_contract）、`graph.svg`、每个查询的
   `query_<id>.svg`、`report.html`、`report.md`、`nodes.csv`、`edges.csv`、
   `graph.jsonld`、`graph.graphml`、`evidence_index.json`。

本例仅用于演示交付物形态，不构成真实论文的回答。
