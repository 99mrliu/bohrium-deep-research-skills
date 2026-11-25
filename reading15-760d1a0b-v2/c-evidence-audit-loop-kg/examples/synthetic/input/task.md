# Task brief — SYNTHETIC example, not real papers

> 本文件是 **SYNTHETIC 合成示例** 的任务书，所有论文内容均为虚构，仅用于演示
> `c-evidence-audit-loop-kg` 的审计-修复闭环流程，不是正式案例答案。

围绕两篇（虚构的）钙钛矿太阳能电池短文构建证据绑定的知识图谱：

1. 抽取实体（论文、研究者、材料、方法、器件、指标、结论）与关系
   （reports / uses / prepared-by / measures / conflicts-with / involves）。
2. 每个实质节点与边必须携带 `source_id` + `paragraph_id` + 原文逐字短引
   （必须是该段落的精确子串）。
3. 正确处理跨篇别名（methylammonium lead iodide ↔ MAPbI3）、同名不同对象
   （两篇中的 TiO2 不是同一物理样品）、跨篇数值冲突（不同条件下的 PCE 不得合并）、
   未报告项（hysteresis index）。
4. 执行 case.json 中的 3 个 query_specs，返回结果子图、证据与无法判定项。
5. 运行审计-修复闭环：审计草案 → 仅修复 repair_queue.json 中的条目 → 复审
   （至多 2 轮），输出 audit_certificate.json。
