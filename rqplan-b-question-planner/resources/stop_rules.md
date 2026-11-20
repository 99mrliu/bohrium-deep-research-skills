# 停止判据（roundlog.py 裁决逻辑）

| 判据 | 触发条件 | 决定 |
|-|-|-|
| evidence_sufficient | 每个 SQ 的累计相关证据 ≥ acceptance_k，或该 SQ 连续 2 轮 new_relevant=0（饱和） | 停止检索，进入覆盖矩阵与综合 |
| marginal_gain_low | 全局连续 2 轮 new_relevant=0，且仍有 SQ 未达标 | 停止检索，未达标 SQ 转入缺口分析（gap 分类） |
| handoff_to_human | 最近 2 笔日志 status=failed（接口异常/限流） | 停止并如实报告，不伪造检索结果 |
| continue | 其余情况 | 按 retrieval_plan.json 继续下一动作 |

## 规则说明

1. 饱和（saturation）是**逐 SQ**判定的：某 SQ 饱和不影响其他 SQ 继续检索。
2. acceptance_k 从该 SQ 的 acceptance 文本中提取（"≥N"）；提取不到时默认 3。
3. 停止决定完全由 rounds.jsonl 的记账数据推出，任何"感觉差不多了"都不构成停止理由；如 Agent 认为判据误判，应先把异议写入该轮 note 再继续，而不是跳过记账。
4. 达到 max_calls 预算但未触发任何停止判据时，按 marginal_gain_low 处理并在 uncertainty 中说明"预算耗尽型停止"。
