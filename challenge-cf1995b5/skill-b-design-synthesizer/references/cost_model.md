# 成本与工期核算模型（cost model）

`design_space.py score` 的核算定义。所有算术用 int / Decimal，无浮点误差；
每个输出行都带 `cost_breakdown`，任何数字可按本文件手工重算。

## 1. 样本数

```
n_conditions = 设计中去重后的条件数（候选方案：各因子数组长度之积）
n_samples    = n_conditions × replicates
```

## 2. 设备机时与工期

- 单样本机时来自 `experiment_model.per_sample.equipment_hours`
  （或 `--model` 覆盖文件；缺失时工期记 unknown，输出 partial）。
- 设备集合 = `resource_contract.equipment` ∪ 从 `equipment_domain_note`
  文本中解析出的内嵌 JSON 设备（按 id 对账去重，列表优先）。
- 每台设备独立核算：

```
hours_e          = hours_per_sample_e × n_samples        (Decimal)
weekly_capacity  = slots_per_week × slot_hours           (小时/周)
weeks_e          = ceil(hours_e / weekly_capacity)       (向上取整)
```

- **并行假设**：不同设备可并行预约、并行占用；同一设备内样品串行排队。
  因此 `est_days = max_e(weeks_e) × 7`，取最大值的设备为**关键设备**。
- 若实际工艺要求两台设备串行衔接（如旋涂后必须立即退火），本模型给出
  的是工期下界；在 plan.md 风险节声明，或将单样本机时合并到单一设备。

## 3. 成本

```
设备成本   = Σ_e hours_e × price_per_hour_e
试剂成本   = Σ_r ceil(qty_r / pack_size_r) × pack_size_r × unit_price_r
qty_r      = per_sample_reagent_r × n_samples
总成本     = 设备成本 + 试剂成本
```

- **pack_size 向上取整**：试剂只能整包购买。例：需 10.5 g、pack 10 g
  → 买 2 包 = 20 g，按 20 g 计价。这是候选方案最常见的少报成本来源
  （把"包数"当"克数"乘单价）。
- 货币单位取 `resource_contract.currency`；合同为前瞻约定，所有价格
  写进方案时必须保留 disclaimer，不得写成已确认报价。

## 4. 可行性三项布尔 + 重复约束

| 字段 | 定义 |
|---|---|
| `in_domain` | 每个条件点的每个参数值都落在 parameter_domains（range 须恰在 min+k·step 网格上；enum 须在 values 内） |
| `within_budget` | 核算总成本 ≤ budget_cap（自报 total_cost 不参与判定） |
| `within_deadline` | est_days ≤ deadline_days（自报 est_days 不参与判定） |
| `replicates_ok` | replicates ≥ min_replicates（默认 2，可 `--min-replicates` 调整） |
| `overall` | 上述全部为真；任一为 false → 进入 reject_reasons；任一为 unknown → 不推荐（honest partial） |

## 5. 自报数对账（仅候选方案）

- `declared_total_mismatch`：自报 total_cost ≠ cost_items 小计之和；
- `declared_vs_computed_cost`：自报总成本 ≠ 脚本核算总成本；
- `declared_vs_computed_days`：自报 est_days ≠ 脚本核算 est_days。

这些进 `consistency_warnings`，写入 result.json 的 candidate_assessment；
是否否决以**核算值**为准，不以自报值为准。
