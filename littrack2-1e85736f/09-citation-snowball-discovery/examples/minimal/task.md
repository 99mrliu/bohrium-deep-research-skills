# 任务说明（合成示例，synthetic）

围绕"固态电池中锂枝晶问题"做最新文献发现与追踪的一轮滚雪球验证：

1. 以 `seed-a`、`seed-b` 两颗种子文献为起点，用 `materials/reference_graph.json`
   做一轮 backward（参考文献）与 forward（被引）扩展；引文边只取图谱文件。
2. 将扩展候选与 `materials/crossref_response.json` 中的关键词检索候选
   （查询词：`lithium`, `dendrite`）做并集合并，给出
   graph_only / keyword_only / both 三分。
3. 量化图谱渠道互补增益，并对每条 graph_only 候选解释为何被关键词渠道漏检
   （证据必须指向材料原文）。
4. 窗口为 2024-01-01 至 2026-12-31；窗口外条目标记为 context，不混入新发现。
5. dangling reference 与缺失种子单独列出，诚实报告。

本示例数据全部为合成（见 case.json 的 synthetic_note），不冒称真实文献。
最终输出写 `output/result.json`，含 case_id 与 output_contract 全部字段。
