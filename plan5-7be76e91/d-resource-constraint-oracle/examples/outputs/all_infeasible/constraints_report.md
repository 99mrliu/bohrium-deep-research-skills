> 合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与裁决逻辑，非正式案例结果或真实实验室/供应商数据。

# 资源约束裁决报告（constraints_report）

- case_id: case-syn-resource-001
- 基准日 reference_date: 2026-01-05
- 截止 deadline: 2026-03-31

| 方案 | verdict | feasible_after | blocking 数 | warning 数 |
| --- | --- | --- | --- | --- |
| Q1 | infeasible | - | 1 | 0 |
| Q2 | infeasible | - | 1 | 0 |
| Q3 | infeasible | - | 1 | 0 |

## Q1 — infeasible
- [BLOCKING] equipment_booking_conflict：设备 PRESS-01 在需求窗口 [2026-01-05, 2026-03-15) 内没有 >= 5 天的连续空档（档期表：[{"start": "2026-01-05", "end": "2026-03-31", "note": "大修，整个需求窗口全占"}]）。
- 注记：耗材 MAT-LATP 预计 2026-01-15 到货（货期 10 天），构成启动约束。
- 注记：审批 APPR-HT（高温炉使用安全审批）已获批。

## Q2 — infeasible
- [BLOCKING] consumable_lead_time_exceeded：耗材 MAT-AU（金靶材）货期 120 天，预计 2026-05-05 到货，晚于需求截止 2026-02-01。
- 注记：审批 APPR-HT（高温炉使用安全审批）已获批。

## Q3 — infeasible
- [BLOCKING] parameter_window_conflict：参数 temperature_C 空交集：方案要求 [1100, 1200] ∩ (设备极限 [20, 1150] ∩ 契约域 [600, 1050] = 允许 [600, 1050]) = ∅。
- 注记：耗材 MAT-AL2O3（氧化铝坩埚）现货，立即可用。
- 注记：审批 APPR-HT（高温炉使用安全审批）已获批。

## 全部方案不可行 — relax_hints（解除条件）

### Q1
- 解除条件：与设备 PRESS-01 的档期持有方协商让出 >= 5 天连续空档；或将需求窗口 [2026-01-05, 2026-03-15) 顺延/放宽（需契约方批准）；或改用同能力替代设备。

### Q2
- 解除条件：为耗材 MAT-AU 找到现货/更短货期供应商（货期 <= 需求截止 2026-02-01），或将需求截止顺延至 2026-05-05 之后（需契约方批准）。

### Q3
- 解除条件：把方案参数 temperature_C 的要求窗口 [1100, 1200] 收缩/平移到允许区间 [600, 1050]（设备极限 ∩ 契约域）之内；若契约域可协商，则向契约方申请放宽参数域。
