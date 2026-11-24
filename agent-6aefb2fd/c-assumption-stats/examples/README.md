# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用固定种子程序生成的玩具数据（3 组 ×40 行 / 120 行回归，与任何正式
> 案例无关），仅用于说明接口与决策树分流；输出**不是**正式案例结果。

## 运行

```
python3 examples/make_example.py /tmp/ps-example
```

## 示例做了什么

1. 组间模式：三个合成特征——`feat_normal`（正态、组间有差异）、`feat_skewed`
   （对数正态、有差异）、`feat_null`（无差异）。引擎裁决：正态 → one_way_anova
   （η²）；偏态 → kruskal_wallis + Dunn（Bonferroni）；零效应不显著。
   `discrimination_ranking` 首位为 feat_normal；特征族 Bonferroni α=0.05/3≈0.0167。
2. 回归模式：y = 2·x1 − x2 + 噪声，R²>0.95，标准化 β_x1>0>β_x2，残差正态性、
   VIF 与"相关≠因果"声明均在输出中。

## 预期打印（节选）

```
PREMISE_STATS_STATUS: ok features=3 bonferroni_significant=2/3 top=[{'feature': 'feat_normal', ...}]
CHECK OK: 正态→ANOVA / 偏态→KW+Dunn / 零效应→不显著；排序首位 feat_normal；Bonferroni α=0.0167
PREMISE_STATS_STATUS: ok n=120 r2=0.99...
CHECK OK: 回归 R²=0.99...，β_x1=0.8... > 0 > β_x2=-0.4...，强制因果声明在位
SYNTHETIC EXAMPLE PASSED -> /tmp/ps-example
```
