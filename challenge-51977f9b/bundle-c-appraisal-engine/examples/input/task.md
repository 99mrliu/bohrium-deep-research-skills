# 任务说明（合成示例 / synthetic, illustrative）

问题：正念干预对医护人员职业倦怠的效果——随机对照试验的系统综述。

已给定 6 篇合成研究（`included.json` 与 `sources/` 下文本，全部虚构）。
请：

1. 按研究类型（RCT）选择/配置质量评价量表，写入 `rubric.json` 并通过
   `rubric_check.py` 校验；
2. 对每篇研究的每个维度给出判定，判定行必须带 `basis_location` 与
   verbatim 的 `basis_quote`；
3. 用 `appraise.py` 确定性重算各研究总分与风险等级；
4. 对 3 条候选论断（`claims.jsonl`）用 `sensitivity.py` 做剔除高风险
   研究后的敏感性分析，unsupported 论断必须改写或移入 uncertainty；
5. 组装 result.json：结论按 stable/weakened/unsupported 标注，
   逐维度判定进 evidence_matrix，争议与不确定项进 uncertainty。
