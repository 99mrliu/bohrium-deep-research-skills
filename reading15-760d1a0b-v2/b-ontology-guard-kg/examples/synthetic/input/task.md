# 任务说明（SYNTHETIC example, not real papers）

> 本任务为合成示例，两篇"论文"均为虚构，仅用于演示 b-ontology-guard-kg 技能包。

给定两篇关于 MAPbI3 钙钛矿太阳能电池的短文（primary: 界面工程效率；secondary:
湿热老化稳定性），构建一个受封闭本体约束的知识图谱：

1. 抽取实体（material / method / sample / metric / condition / claim / researcher / task）
   与类型化关系，所有节点与边必须带 source_id + paragraph_id + 精确子串 quote。
2. 所有抽取必须通过封闭本体校验（references/ontology.json）；违规条目进入隔离区，
   只允许一轮有界修复。
3. 处理跨篇别名（MAPbI3 ↔ methylammonium lead iodide）、同名不同物（两篇的 TiO2
   电子传输层是不同样品）、以及不同条件下的数值冲突（21.1% 初始 vs 18.7% 老化后，
   不得合并）。
4. 执行 case.json 中的 3 个 query_specs，并组装镜像 output_contract 的 result.json。
