# cost-schema.md — 成本模型与成本表字段规范

本规范定义 cost-ledger 技能三个脚本之间流转的 JSON 结构。所有金额/时间数值
以字符串形式携带（Decimal 语义），展示时保留两位小数；任何字段都必须带显式
单位声明。

## 1. 资源/价格/预约契约（输入，cost_model.py 读取）

```json
{
  "machine_rate":       {"value": 180, "unit": "CNY/hour"},
  "consumable_price":   {"value": 45,  "unit": "CNY/portion"},
  "sample_prep_time":   {"value": 0.5, "unit": "hour/sample"},
  "daily_machine_hours":{"value": 6,   "unit": "hour/day"},
  "budget":             {"value": 8000,"unit": "CNY"},
  "deadline":           {"value": 10,  "unit": "working_day"},
  "typical_run_hours":  {"value": 2.5, "unit": "hour"},
  "unit_conversions":   {"min": {"to": "hour", "divide_by": 60}}
}
```

| 字段 | 声明单位 | 必需 | 含义 |
|---|---|---|---|
| machine_rate | CNY/hour | 是 | 机时费率（元/小时） |
| consumable_price | CNY/portion | 是 | 耗材单价（元/份） |
| sample_prep_time | hour/sample | 否 | 单样品制备时间（小时/样品） |
| daily_machine_hours | hour/day | 是 | 每日可用机时（预约窗口，小时/天） |
| budget | CNY | 是 | 总预算（元），负数为非法契约 |
| deadline | working_day | 是 | 截止（工作日），必须为正 |
| typical_run_hours | hour | 否 | 单 run 机时的口径声明（用于单位一致性锚点） |
| unit_conversions | — | 否 | 契约自带换算白名单，见 unit-rules.md |

## 2. cost_model.json（cost_model.py 产物）

```json
{
  "schema_version": "cost-model/1.0",
  "status": "ok | partial | refused | error",
  "declared_units": {"machine_rate": "CNY/hour", "...": "..."},
  "fields": {
    "machine_rate": {"value": "180", "unit": "CNY/hour", "source": "contract:resource_contract.json"}
  },
  "conversions_applied": [{"field": "...", "note": "...", "source": "..."}],
  "uncertainty": ["..."]
}
```

- `fields[*].value` 为字符串形式的 Decimal；`unit` 恒等于声明单位（换算已在
  解析期完成并记录于 `conversions_applied`，绝不静默）。
- `status=refused` 时下游脚本不得运行核算，须把 `reason` 透传进 result.json。

## 3. 候选方案版本（输入，plan_costing.py 读取）

```json
{"plans": [{
  "version": "v2_sequential_10",
  "runs": 10,
  "hours_per_run": {"value": 2.5, "unit": "hour"},
  "samples_per_run": 1,
  "replicates": 1,
  "consumables_per_run": {"value": 2, "unit": "portion"},
  "predicted_response": {"value": 88, "direction": "maximize", "unit": "yield_percent"}
}]}
```

| 字段 | 类型 | 必需 | 含义 |
|---|---|---|---|
| version | string | 是 | 版本标识 |
| runs | number | 是 | 实验 run 数（>=0） |
| hours_per_run | {value,unit} | 是 | 单 run 机时；unit 必须等于声明 hour 或经白名单换算 |
| samples_per_run | number | 是 | 每 run 样品数 |
| replicates | number | 否（默认 1） | 重复次数 |
| consumables_per_run | {value,unit} | 是 | 每 run 耗材量；unit 必须为 portion |
| predicted_response | {value,direction,unit} | 建议 | 预测响应；缺失则该版本不参与 Pareto |

## 4. cost_sheet.json（plan_costing.py 产物）

每版本条目：

| 字段 | 含义 |
|---|---|
| total_machine_hours | 总机时 = runs × hours_per_run |
| total_consumables | 总耗材 = runs × consumables_per_run |
| machine_cost | 机时费 = total_machine_hours × machine_rate |
| consumable_cost | 耗材费 = total_consumables × consumable_price |
| total_cost | 总成本 = machine_cost + consumable_cost |
| total_days | 总历时（工作日）= ceil(total_machine_hours / daily_machine_hours) |
| total_samples | 总样品数 = runs × samples_per_run × replicates |
| throughput_samples_per_day | 通量 = total_samples / total_days |
| total_prep_hours | 样品制备总时间（单列，不计入工作日口径） |
| within_budget / within_deadline | 布尔 verdict |
| trace | 算术痕迹字符串数组，每行 "lhs = 代入数字 = 结果" |

## 5. pareto.json（pareto.py 产物）

- `frontier`：非支配版本（按成本升序）；
- `dominated`：被支配版本，附 `dominated_by`；
- `recommendation`：预算+截止双约束可行集内响应最大（同响应取成本最低）的
  版本，附 `tradeoffs` 取舍陈述（相对最便宜可行版、相对最高响应版）；
- 无可行版本时 `recommendation=null`、`status=partial`，如实写入 uncertainty。
