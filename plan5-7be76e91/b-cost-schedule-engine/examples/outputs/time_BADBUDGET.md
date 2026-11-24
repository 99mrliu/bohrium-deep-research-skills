> 合成示例 / SYNTHETIC EXAMPLE —— booby-trap 负例：总成本 30000 超 case 预算 20000，必须被 time_model 预算门以 exit 3 (over_budget) 捕获

# 时间模型台账 — 方案 BADBUDGET

- 状态: ok
- 换算: 1 day = 8 h（来源: plan_record.workday_hours）
- **labor_hours（人力工时）: 56 h**
- **elapsed_days（自然周期）: 7 天**（elapsed_hours=56 h）
- 门判定 gate_status: **over_budget**

| # | 阶段 | 时长 | 单位 | 折算小时 | 返工概率 | 返工代价 | 期望返工(h) | 计入 | 来源 |
|---|------|------|------|----------|----------|----------|--------------|------|------|
| 0 | 样品准备 | 1 | days | 8 | - | - | - | labor+elapsed | - |
| 1 | 实验执行 | 5 | days | 40 | - | - | - | labor+elapsed | - |
| 2 | 数据分析 | 1 | days | 8 | - | - | - | labor+elapsed | - |

## 逐阶段合计（小时，含期望返工）

- 样品准备: 8 h（其中计人力 8 h）
- 设备排期等待: 0 h（其中计人力 0 h）
- 实验执行: 40 h（其中计人力 40 h）
- 表征排队: 0 h（其中计人力 0 h）
- 数据分析: 8 h（其中计人力 8 h）
- 返工缓冲: 0 h（其中计人力 0 h）

## 硬约束门

- budget: {"limit": "20000", "status": "over_budget", "total_cost": "30000"}
- deadline: {"elapsed_days": "7", "limit_days": "30", "status": "pass"}
