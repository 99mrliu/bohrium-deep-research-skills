# examples/ — 合成示例（synthetic example）

**本目录全部为合成示例**：所有价格、预约窗口与预测响应均为前瞻性计划数据，
非真实报价、非真实实验结果。

## 目录

- `synthetic-input/`
  - `case.json` — 案例输入（case_id、output_contract 三字段 experiment_plan /
    evidence_and_risk / confirmation_items、材料路径）；
  - `resource_contract.json` — 合成资源预约契约：机时 180 元/小时、耗材 45 元/份、
    单样品制备 0.5 h、每日可用机时 6 h、总预算 8000 元、截止 10 个工作日；
  - `resource_contract_bad_unit.json` — **负例契约变体**：单 run 机时单位写成
    "分钟"且未提供 unit_conversions 换算关系；
  - `plans.json` — 三个候选方案版本：v1 全网格 27 点（预测响应 92）、
    v2 序贯 10 点（88）、v3 筛选 6 点（74）；
  - `materials/lab_notice.md` — 材料文本（文本兜底解析的兜底来源）。
- `synthetic-output/` — 真实端到端运行产物（已目检，算术痕迹经人工核对）。

## 复现命令（在 bundle 根目录执行）

```bash
# (a) 成本模型解析
python3 scripts/cost_model.py \
  --case examples/synthetic-input/case.json \
  --contract examples/synthetic-input/resource_contract.json \
  --materials examples/synthetic-input/materials \
  --out examples/synthetic-output/cost_model.json        # 期望 exit 0, status=ok

# (b) 三版本成本表（v1 应被标 within_budget=false）
python3 scripts/plan_costing.py \
  --cost-model examples/synthetic-output/cost_model.json \
  --plans examples/synthetic-input/plans.json \
  --out examples/synthetic-output/cost_sheet.json        # 期望 exit 0, status=ok

# (c) 成本-响应 Pareto 前沿与推荐
python3 scripts/pareto.py \
  --cost-sheet examples/synthetic-output/cost_sheet.json \
  --out examples/synthetic-output/pareto.json            # 期望 exit 0, status=ok

# (d) 负例：分钟单位契约变体被拒（非零退出，产物 unit_reject.json）
python3 scripts/cost_model.py \
  --case examples/synthetic-input/case.json \
  --contract examples/synthetic-input/resource_contract_bad_unit.json \
  --out examples/synthetic-output/unit_reject.json       # 期望 exit 2, status=refused
```

## 期望结果（人工核对基准）

| 版本 | 总机时 | 总成本 | 历时 | 通量 | within_budget | within_deadline |
|---|---|---|---|---|---|---|
| v1_full_grid_27 | 67.50 h | **14580.00 元** | 12 工作日 | 2.25 样品/天 | **false**（超 6580.00 元） | false |
| v2_sequential_10 | 25.00 h | 5400.00 元 | 5 工作日 | 2.00 样品/天 | true | true |
| v3_screening_6 | 12.00 h | 2430.00 元 | 2 工作日 | 3.00 样品/天 | true | true |

人工核对示例（v1 算术痕迹）：`total_cost = machine_cost(12150.00 元) +
consumable_cost(2430.00 元) = 14580.00 元`，其中
`12150.00 = 27 runs × 2.5 h × 180 元/h`、`2430.00 = 54 份 × 45 元/份` ——
手算一致。

Pareto：三版本成本-响应单调（钱越多响应越高），均在前沿上、互不支配；
预算 8000 元内可行集为 {v2, v3}，推荐 **v2_sequential_10**：
- 相对最便宜可行版 v3 多花 2970.00 元，换 14.00 yield_percent 响应；
- 相对最高响应版 v1 牺牲 4.35% 响应（92 → 88），省 9180.00 元（v1 超预算超期，本不可行）。

负例：cost_model.py 以 exit 2 拒绝，reason 指出单位 '分钟' 与声明单位 'hour'
不一致且契约未提供换算关系——绝不静默换算。

`synthetic-output/result.json` 演示了按 harness 契约组装的最终结果
（case_id 照抄、output_contract 三字段齐全、status=success、sources /
uncertainty / change_log）。
