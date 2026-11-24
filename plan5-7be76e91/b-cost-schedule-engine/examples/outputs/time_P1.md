> 合成示例 / SYNTHETIC EXAMPLE —— P1 便宜但慢；条目为虚构演示值

# 时间模型台账 — 方案 P1

- 状态: ok
- 换算: 1 day = 8 h（来源: case.workday_hours）
- **labor_hours（人力工时）: 72 h**
- **elapsed_days（自然周期）: 27 天**（elapsed_hours=216 h）
- 门判定 gate_status: **pass**

| # | 阶段 | 时长 | 单位 | 折算小时 | 返工概率 | 返工代价 | 期望返工(h) | 计入 | 来源 |
|---|------|------|------|----------|----------|----------|--------------|------|------|
| 0 | 样品准备 | 2 | days | 16 | - | - | - | labor+elapsed | contract_pricing.example.md / §2 |
| 1 | 设备排期等待 | 10 | days | 80 | - | - | - | elapsed_only | contract_pricing.example.md / §2.1 |
| 2 | 实验执行 | 5 | days | 40 | - | - | - | labor+elapsed | - |
| 3 | 表征排队 | 8 | days | 64 | - | - | - | elapsed_only | - |
| 4 | 数据分析 | 2 | days | 16 | - | - | - | labor+elapsed | - |

## 逐阶段合计（小时，含期望返工）

- 样品准备: 16 h（其中计人力 16 h）
- 设备排期等待: 80 h（其中计人力 0 h）
- 实验执行: 40 h（其中计人力 40 h）
- 表征排队: 64 h（其中计人力 0 h）
- 数据分析: 16 h（其中计人力 16 h）
- 返工缓冲: 0 h（其中计人力 0 h）

## 硬约束门

- budget: {"limit": "20000", "status": "pass", "total_cost": "8480.9"}
- deadline: {"elapsed_days": "27", "limit_days": "30", "status": "pass"}
