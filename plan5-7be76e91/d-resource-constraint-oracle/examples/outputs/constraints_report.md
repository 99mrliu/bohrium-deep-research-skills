> 合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与裁决逻辑，非正式案例结果或真实实验室/供应商数据。

# 资源约束裁决报告（constraints_report）

- case_id: case-syn-resource-001
- 基准日 reference_date: 2026-01-05
- 截止 deadline: 2026-03-31

| 方案 | verdict | feasible_after | blocking 数 | warning 数 |
| --- | --- | --- | --- | --- |
| P1 | feasible_now | - | 0 | 0 |
| P2 | feasible_after | 2026-01-31 | 0 | 0 |
| P3 | infeasible | - | 1 | 0 |

## P1 — feasible_now
- 注记：耗材 MAT-AL2O3（氧化铝坩埚）现货，立即可用。
- 注记：审批 APPR-HT（高温炉使用安全审批）已获批。
- 注记：审批 APPR-XRD（XRD 机时使用审批）已获批。

## P2 — feasible_after
- 最早可启动（所有启动约束的最大者）：**2026-01-31**
- 注记：设备 PRESS-01（阶段 execute）首个 >= 5 天空档自 2026-01-31 起，构成启动约束。
- 注记：耗材 MAT-LATP 预计 2026-01-15 到货（货期 10 天），构成启动约束。
- 注记：审批 APPR-HT（高温炉使用安全审批）已获批。
- 注记：审批 APPR-XRD（XRD 机时使用审批）已获批。

## P3 — infeasible
- [BLOCKING] parameter_window_conflict：参数 temperature_C 空交集：方案要求 [1100, 1200] ∩ (设备极限 [20, 1150] ∩ 契约域 [600, 1050] = 允许 [600, 1050]) = ∅。
- 注记：耗材 MAT-AL2O3（氧化铝坩埚）现货，立即可用。
- 注记：审批 APPR-HT（高温炉使用安全审批）已获批。
