# 抽取 Schema 与定位符（locator）约定

> 模型的唯一职责：把 case 材料中的数值**逐字（verbatim）**抽取成结构化 JSON，并给出可回溯的定位符。
> **禁止**模型做任何算术（连"顺手四舍五入"也不行）——一切数值结论由脚本实算。

## 文件结构（每个方案版本一个 extraction 文件）

```json
{
  "plan_id": "PLAN-V1",
  "budget_items": [
    {
      "name": "胎牛血清",
      "unit_price": 800.00,
      "quantity": 2,
      "currency": "CNY",
      "stated_subtotal": 1600.00,
      "locator": "PLAN-V1#预算表#行2"
    }
  ],
  "schedule_steps": [
    {
      "id": "S1",
      "name": "细胞复苏",
      "duration_hours": 24,
      "depends_on": [],
      "resource": "CO2培养箱",
      "locator": "PLAN-V1#进度表#行1"
    }
  ],
  "parameters": [
    {"name": "培养温度", "value": 37, "unit": "°C", "locator": "PLAN-V1#参数表#行1"}
  ],
  "materials": [
    {"name": "胎牛血清", "quantity": 2, "unit": "瓶", "locator": "PLAN-V1#物料表#行1"}
  ],
  "samples": [
    {"name": "细胞上清样本", "count": 24, "locator": "PLAN-V1#样本说明#行1"}
  ]
}
```

## 字段规则

| 字段 | 规则 |
|---|---|
| `plan_id` | 非空字符串，必须与 case.json 中该版本的标识一致 |
| `unit_price` / `quantity` | 有限数，`unit_price ≥ 0`，`quantity > 0`；**按原文逐字抄写**，单位不同就原样记录并在 `name` 或备注中保留原文单位，不自行换算 |
| `currency` | 1–8 字符，如 `CNY` |
| `stated_subtotal` | 可选。仅当原文**明确写了**小计时才填；脚本会复算 `unit_price × quantity` 并对比，漂移 >0.5% 即标记 unverified |
| `duration_hours` | > 0 的有限数。若原文是分钟/天，**先在 extraction 中换算成小时是不允许的**——应保留原文数值与单位，在 `name` 或 locator 备注中注明，由脚本/人统一换算；若确需模型换算，必须把原文和换算式写进 locator |
| `depends_on` | 字符串数组，元素必须是本文件内已声明的 `id`；无依赖给 `[]` |
| `value` / `unit` | `value` 为数值或数值字符串；`unit` 非空（无单位写 `"1"` 并在 locator 说明） |
| `count` | 正整数 |

## locator 约定

格式：`<plan_id>#<小节/表名>#<行号或条目号>`，例如 `PLAN-V2#预算表#行4`、`PLAN-V3#进度与资源#步骤S2`。

- 必须非空；必须指向 case 材料中**真实存在**的位置（inspect_case.py 给出的 JSON 路径 + 行/条目）。
-  reviewer 凭 locator 应能在原文中找到与 extraction 完全一致的数字。
- 模型**不得**凭记忆/常识补数；找不到的数值宁可不抽取该条目，并在最终 uncertainty 中说明缺口。

## 铁律

1. 数字逐字抄写，永不四舍五入、永不估算。
2. 模型输出只经过 `validate_extraction.py` 校验后才允许进入实算脚本。
3. 任何脚本无法从抽取操作数复算出来的数字，一律标记 `unverified`，不得采信（见 arithmetic_rules.md）。
