> 合成示例（synthetic）预期输出副本，非正式案例结果；时间戳字段以实际运行为准。

# 容差裁决报告（tolerance adjudication）

- 生成时间：2026-11-23T16:05:34+00:00
- 容差注册时间：2026-11-23T16:05:32+00:00
- preregistration_violation：**false**

| 方法 | 指标 | 论文值 | 中位 | 容差 | 偏差(abs) | 判定 | 告警 |
|---|---|---|---|---|---|---|---|
| method_a | ablation_score | — | — | ±— | — | **not_comparable** |  |
| method_a | accuracy | 0.152 | 0.15 | ±0.01 | 0.002 | **within_tolerance** |  |
| method_a | latency_ms | 72.1 | 72.1 | ±0.05 | 0 | **within_tolerance** |  |
| method_a | rouge_l | 0.412 | 0.413 | ±0.0005 | 0.001 | **stochastic_fluctuation** |  |
| method_a | throughput | 1.2e3 | 1205 | ±50 | 5 | **within_tolerance** |  |
| method_b | ablation_score | — | — | ±— | — | **not_comparable** |  |
| method_b | accuracy | 0.152 | 0.121 | ±0.01 | 0.031 | **systematic_deviation** |  |
| method_b | latency_ms | 72.1 | 75.1 | ±0.05 | 3 | **systematic_deviation** |  |
| method_b | rouge_l | 0.412 | 0.4 | ±0.0005 | 0.012 | **insufficient_runs** |  |
| method_b | throughput | 1.2e3 | — | ±50 | — | **missing** |  |

## 汇总

- total: 10
- within_tolerance: 3
- stochastic_fluctuation: 1
- systematic_deviation: 2
- exceeds_tolerance: 0
- not_comparable: 2
- missing: 1
- insufficient_runs: 1

> attribution_hint 仅为机械建议（numerical_noise / systematic / none），最终归因由 agent 结合证据决定；合成代码 ≠ 作者原代码，合成数据上的 within_tolerance 不能写成论文数值复现。
