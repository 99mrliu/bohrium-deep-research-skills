# 门控规则与一致性检查

## 门控规则（feasibility_gate.py 强制）

| 规则 | 条件 | verdict |
|---|---|---|
| G1 | 任一前提 status=blocked | not_feasible（列出全部 blocker） |
| G2 | 无 blocked，但存在 unknown 或 backing=assumption | conditional（列出条件/待核清单） |
| G3 | 全部 ok 且全部 source | feasible |
| G4 | 台账为空 | insufficient_evidence |

语义：

- `not_feasible` 不是"枪毙"，是"当前约束下不成立"；blocker 清单即返工清单，解除 blocker 后重跑门控。
- `conditional` 是最常见的诚实结论：条件清单中的每一项都是立项前必须关闭的事项（核实数据许可、确认算力到位、补做预实验）。
- `feasible` 门槛刻意很高（全部前提有来源支持）；达不到就老老实实 conditional。
- `insufficient_evidence` 用于材料完全不支持判断的场景，配合 result.json 的 partial。

## 一致性违例（退出码 1，不得交付）

| 规则 | 内容 |
|---|---|
| Y1 | backing=source 但 evidence_ref 为空 |
| Y2 | backing=assumption 但 note 为空 |
| Y3 | category/status/backing 取值非法 |
| Y4 | id 重复 |

## 风险登记册

全部 unknown 与 assumption 前提自动入册（risk_register.md）。登记册的意义：让评审者一眼看到结论押在哪些未核实的赌注上；结项复查时逐条核销。
