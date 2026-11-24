# 结论-证据绑定规范（claim-evidence-binding）

让每一句结论都能被机器追问「证据在哪」，是本 bundle 的第二重心。

## 绑定协议

1. result.json 含 `claims` 数组，每个元素：
   ```json
   {"id": "H1", "outcome": "score", "comparison": "对照组 vs 处理组",
    "direction": "increase|decrease|no_difference", "significant": true,
    "p": 7.6e-05, "alpha": 0.05,
    "effect_size": {"name": "hedges_g", "value": -0.155, "ci95": [-0.217, -0.093]},
    "practical_note": "效应量 Hedges g = …[ev:H1]",
    "sentence": "在 α=0.05 水平下，…。[ev:H1]"}
   ```
   附加机器核对字段：`method / group_a / group_b / mean_a / mean_b /
   diff / diff_label / magnitude / p_raw（事后比较）`。
2. report.md「结果解释」章节中，每句结论句（含 统计学意义/效应量/
   置信区间为/中位数差 的散文句）以 `[ev:H<k>]` 结尾，ID 与 claims 一一对应。
3. `claims[].sentence` 与报告句**逐字一致**（含标签），
   句中数值与存储值在四舍五入容差内一致。

## claim_bind.py 核验项与违例码

| 码 | 含义 | 判定 |
|---|---|---|
| DANGLING_EVIDENCE | 结论句缺 [ev:ID]，或 ID 不可解析 | 章节句扫描 + 全文标签解析 |
| DIRECTION_MISMATCH | direction 与存储均值差符号矛盾 | 显著⇔increase/decrease 且符号一致；不显著⇔no_difference |
| SIGNIFICANCE_MISMATCH | significant 与 p<alpha 矛盾 | 直接比较存储值 |
| NUMBER_MISMATCH | 句中 p/效应量/CI 端点/均值差/中位数差与存储不符 | 容差 = 0.51×10^(-展示小数位) |
| SENTENCE_DRIFT | claims.sentence 与报告句不逐字一致 | 子串精确匹配 |

## 为什么要求逐字一致

报告句与结构化存储一旦允许「意思相同」，就会出现静默漂移：模型改写句子时
顺手把 p=0.041 改成 p=0.014、把「不具有」漏成「具有」。逐字一致 + 数值容差
核对把这类漂移变成可拦截的构建错误（见 examples/run_example.sh 埋雷 4）。

## 展示精度约定（改模板必须同步改这里）

- p：4 位小数；`p<0.0001` 记法（claim_bind 校验存储 p 确实 <0.0001）。
- 效应量、CI 端点、均值差/中位数差：3 位小数。
- 事后比较：claim.p 存 **Holm 调整后** p（原始 p 存 p_raw），
  句中写「调整后 p=…」。
