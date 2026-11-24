# 风险方法说明（FMEA + 期望代价 + 回退路径）与本题评分点对应

## 1. 方法概述

本 bundle 把「实验方案比较与选择」中的风险部分做成四段可机检流程：

1. **结构化风险登记（模型完成）**：每条风险必须包含触发条件（trigger_condition）、后果量级（consequence_magnitude，量级+单位）、S/L/D 三维定级、缓解措施、回退动作引用、依据来源。禁止「存在一定风险」这类无触发条件、无量级、无缓解的空话。
2. **FMEA 分级（fmea.py，确定性）**：RPN = S × L × D；按 thresholds.json 内置阈值分为 critical/high/medium/low；定级阈值可用 `--thresholds` 覆盖但必须在输出中声明。critical/high 缺缓解措施 → 质量门 exit 3。
3. **期望代价比较（expected_cost.py，确定性）**：风险调整代价 = base + Σ P(likelihood) × 后果代价 + 缓解投入；likelihood→概率映射内置（1:0.05, 2:0.15, 3:0.35, 4:0.6, 5:0.85），输入可覆盖并声明。多方案时输出对比排序。
4. **回退完备性校验（fallback_graph.py，确定性）**：每条 critical/high 风险必须有 fallback_ref 指向存在的回退动作；回退链（action 的 on_failure_ref）不得成环；给出三态结论：acceptable_risk / needs_expert / infeasible_without_change。缺陷 → exit 3。

## 2. 与本题评分点的对应

| 题目点名的失败 | 本 bundle 的机检对策 |
|---|---|
| 风险写成「存在一定风险」，无触发条件 | trigger_condition 为空 → fmea.py 缺陷 exit 3 |
| 无后果量级 | consequence_magnitude 为空 → exit 3；缺数字量级 → warning 记录 |
| 无缓解措施 | critical/high 的 mitigation 为空 → exit 3 |
| 不区分「可接受风险」与「不可行」 | severity_anchors.md 判据 + fallback_graph.py 三态 verdict |
| 关键失败场景无替代路径 | critical/high 缺 fallback_ref 或悬空引用 → exit 3；回退链成环 → exit 3 |
| 方案比较只看标称成本 | expected_cost.py 输出风险调整代价与多方案排序 |
| 未经确认的建议写成事实 | requires_expert_confirm 的回退使 verdict=needs_expert；SKILL.md 要求 pending 项不得写成事实 |

## 3. 定级与结论的责任边界

- 脚本只做算术与完备性校验，不替代领域判断；S/L/D 的取值由模型依据 severity_anchors.md / likelihood_anchors.json 锚点给出，并在 evidence_source 中注明出处（论文页码、情景契约条目、参数域边界等）。
- 「不可行建议」（infeasible_without_change）是**建议性结论**，写入 result.json 时必须标注「需专家确认」，不得直接写成「该方案不可行」的事实陈述。
- 情景中的价格、货期、契约数字是组织方前瞻性给定的规划数据，引用时必须注明「情景给定」，不得表述为实测或真实供应商报价。
