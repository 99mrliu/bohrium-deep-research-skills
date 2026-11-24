# 容差策略（两级）

## 复算级（A/B 通道一致性）
- 默认 abs_tol=1e-9、rel_tol=1e-9：两条正确实现在正常输入上的差异应在浮点噪声量级。
- DISAGREE 的现实意义不是「谁对」，而是「输入病态或实现有坑」——此时任何单通道结果都不可信。
- 已知病态场景：二阶矩法方差在 mean/σ > 1e6 时失真（这正是要它当通道 A 的原因：能暴露问题）。

## 报告级（claimed vs recomputed）
- 默认 rel_tol=1e-6；领域惯例更宽时（如实验读数 3 位有效数字，rel_tol≈5e-4），
  在 claims.json 逐条设置 rel_tol 并在结论中声明所用容差。
- 禁止为让 claim 通过而无限放宽：rel_tol > 0.05 必须在 uncertainty 中给出理由。

## 结论引用格式
每个数值结论：数值 + (recomputed 值, rel_diff, ledger 路径)。
缺 ledger 路径的数值 = 未复算 = 不可交付。
