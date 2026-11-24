# 统计分析报告 — synth-figforge-demo

- 状态: **ok** | 主数据源: response.csv | 行数: 27→27（清洗后）
- 可复现: seed=20240501, python=3.9.6, 2026-11-24T16:16:29+00:00

## 1. 数据质量与清洗
- 缺失: report_and_exclude（按变量有效 n，不零填不插补）；计数: 无
- 重复: 策略 report_only_keep；检测 1 行，删除 0 行
- 异常值: 1.5×IQR 栅栏只标记不删除；标记: 无

## 2. 描述统计（按组）
### rt（单位：ms）
| 组 | n | 均值 | SD | 中位数 | Q1 | Q3 | min | max | 偏度 |
|---|---|---|---|---|---|---|---|---|---|
| control | 8 | 9.841 | 0.8533 | 9.598 | 9.33 | 10.47 | 8.868 | 11.23 | 0.375 |
| treatA | 9 | 11.77 | 1.207 | 12.06 | 11.68 | 12.45 | 8.893 | 12.84 | -1.628 |
| treatB | 10 | 13.06 | 1.374 | 12.8 | 11.81 | 14.41 | 11.63 | 14.78 | 0.097 |

## 3. 假设检验
| id | 结局 | 设计 | 方法 | 依据码 | 统计量 | df | p | 显著 |
|---|---|---|---|---|---|---|---|---|
| a1 | rt | k_group | Kruskal-Wallis | NON_NORMAL_OR_SMALL_N->KRUSKAL_WALLIS | H=14.36 | 2 | p=0.0008 | 是 |

## 4. 效应量与 95% 置信区间
- **a1** (rt, Kruskal-Wallis): {"effect": {"epsilon_squared": 0.5150433983601923}, "ci": {}}

## 5. 结果解释
【rt】按 group 比较（3 组，ms）：Kruskal-Wallis（依据 NON_NORMAL_OR_SMALL_N->KRUSKAL_WALLIS），H=14.36，df=2，p=0.0008，α=0.05 → 统计上显著。ε²=0.5150（效应大）。事后两两比较（同路线 + Holm 校正）：2/3 对显著。注意：统计显著不等于实际意义，结论不能被表述为“证明”；单位=ms。

## 6. 局限性
- 推断基于报告数据的假设门控路线；非参路线统计量为渐近近似。
- 未注明确认单位的变量在图注中标记“单位未注明”。

## 7. 图表
<!-- FIGURES:BEGIN -->
图表文件（详见 figures.md，含每组 n 与单位图注）：
- `fig1.svg` — 图1｜箱线图+抖动散点｜rt 按 group 分组比较（单位：ms）｜组 control：n=8，均值=9.84，SD=0.85；组 treatA：n=9，均值=11.77，SD=1.21；组 treatB：n=10，均值=13.06，SD=1.37｜检验：Kruskal-Wallis H(2)=1…
- `fig2.svg` — 图2｜ECDF 分布形态｜rt 按 group 分组比较（单位：ms）｜组 control：n=8，均值=9.84，SD=0.85；组 treatA：n=9，均值=11.77，SD=1.21；组 treatB：n=10，均值=13.06，SD=1.37｜检验：Kruskal-Wallis H(2)=…
<!-- FIGURES:END -->

## 8. 来源与复现
- response.csv: sha256=5ef4140455a583c67859f6abe8edd7897742c3926ebd9b42f2d9a18e6e8a3bf9, 27 行 × 2 列
