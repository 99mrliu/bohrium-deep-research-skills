> 合成示例 / SYNTHETIC EXAMPLE —— P2 贵但快；条目为虚构演示值

# 时间模型台账 — 方案 P2

- 状态: ok
- 换算: 1 day = 8 h（来源: case.workday_hours）
- **labor_hours（人力工时）: 49.6 h**
- **elapsed_days（自然周期）: 9.2 天**（elapsed_hours=73.6 h）
- 门判定 gate_status: **pass**

| # | 阶段 | 时长 | 单位 | 折算小时 | 返工概率 | 返工代价 | 期望返工(h) | 计入 | 来源 |
|---|------|------|------|----------|----------|----------|--------------|------|------|
| 0 | 样品准备 | 1 | days | 8 | - | - | - | labor+elapsed | - |
| 1 | 设备排期等待 | 2 | days | 16 | - | - | - | elapsed_only | contract_pricing.example.md / §2.2 |
| 2 | 实验执行 | 3 | days | 24 | 0.2 | 1 | 1.6 | labor+elapsed | contract_pricing.example.md / §1.2 |
| 3 | 表征排队 | 1 | days | 8 | - | - | - | elapsed_only | - |
| 4 | 数据分析 | 2 | days | 16 | - | - | - | labor+elapsed | - |

## 逐阶段合计（小时，含期望返工）

- 样品准备: 8 h（其中计人力 8 h）
- 设备排期等待: 16 h（其中计人力 0 h）
- 实验执行: 25.6 h（其中计人力 25.6 h）
- 表征排队: 8 h（其中计人力 0 h）
- 数据分析: 16 h（其中计人力 16 h）
- 返工缓冲: 0 h（其中计人力 0 h）

## 硬约束门

- budget: {"limit": "20000", "status": "pass", "total_cost": "14800"}
- deadline: {"elapsed_days": "9.2", "limit_days": "30", "status": "pass"}
