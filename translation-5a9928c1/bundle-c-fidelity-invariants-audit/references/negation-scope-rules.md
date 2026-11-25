# 否定与限定守恒规则（Bundle C）

## 高危错译模式（审计重点）

1. `did not reduce X` ≠ `reduced X`：否定丢失直接反转结论。
2. `no significant benefit` ≠ `equivalence`：无显著获益不等于等效。
3. `no evidence for an effect` ≠ `evidence of no effect`：证据缺失不等于效应缺失。
4. `may / suggests / indicates` 不得升格为 `proves / demonstrates / shows conclusively`。
5. `approximately / ~ / about` 不得收窄为精确值。
6. 体外/动物/模拟结果不得译为临床疗效（in-vitro detection ≠ clinical efficacy）。
7. 绝对百分点差 ≠ 相对百分比变化（absolute percentage-point difference ≠ relative percent change）。

## 处置

- negation_lost / qualifier_lost 触发后：回到原文句子，确认否定范围与限定词，
  修订译文并重跑审计；确属合法的语气转换（如间接引语）须在 signal_explanation
  写明依据，并进入人工确认清单（--allow-explained）。
- 禁止为清零而删除原文中的限定词（那是改坏正确译文）。
