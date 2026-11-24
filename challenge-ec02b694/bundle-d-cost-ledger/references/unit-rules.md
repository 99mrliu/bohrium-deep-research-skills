# unit-rules.md — 单位声明、换算白名单与拒算规则

成本台账的第一原则：**口径不自洽的账宁可拒算，绝不静默换算。** 本文件定义
cost-ledger 技能的单位制度。

## 1. 声明单位（成本模型的唯一口径）

| 量 | 声明单位 | 说明 |
|---|---|---|
| 机时费率 | CNY/hour | 元/小时 |
| 耗材单价 | CNY/portion | 元/份 |
| 单样品制备时间 | hour/sample | 小时/样品 |
| 每日可用机时 | hour/day | 小时/天（预约窗口） |
| 总预算 | CNY | 元 |
| 截止 | working_day | 工作日 |
| 单 run 机时 | hour | 小时 |

所有下游计算只使用声明单位；cost_model.json 中每个字段的 `unit` 必须等于
声明单位。

## 2. 单位一致性检查（cost_model.py 与 plan_costing.py 共用规则）

对每一个带单位的输入值，按以下顺序处理：

1. **单位 == 声明单位** → 直接采用。
2. **单位缺失**（只有数值没有 unit）→ 按声明单位处理，但必须把该假设显式
   写入 `conversions_applied` / uncertainty（"已记录假设，未做任何换算"）。
3. **单位 != 声明单位，但契约自带 `unit_conversions` 白名单给出换算关系**
   （如 `{"min": {"to": "hour", "divide_by": 60}}`）→ 执行换算，把换算式
   （原值、单位、除数、结果）写入 `conversions_applied` 或算术痕迹。
   白名单只接受契约显式声明的关系；脚本不内置任何跨尺度换算表。
4. **单位 != 声明单位，且换算关系缺失** → **拒绝**：
   - cost_model.py：写出 status=refused 的 JSON（含原因与 uncertainty 播种），
     退出码 2；
   - plan_costing.py：该版本标记 status=rejected 并说明原因；若全部版本被
     拒，整体 status=refused，退出码 2。

### 拒算示例（负例）

契约写 `typical_run_hours: {"value": 150, "unit": "分钟"}` 且未提供
`unit_conversions` → cost_model.py 拒绝，理由：单位 '分钟' 与声明单位
'hour' 不一致且无换算关系。即使 150 分钟显然等于 2.5 小时，也绝不擅自换算——
因为接受一次"显然"的换算，就会放过下一次"不显然"的口径错误（小时/班次、
份/盒、万元/元）。

## 3. 文本兜底的单位规则

从材料文本解析数字时（cost_model.py 的材料兜底），正则只匹配带**同义单位**
的写法（小时/h、元、份、工作日），不接受任何需要跨尺度换算的写法
（如"分钟""万元"）。匹配不到就留白并记入 uncertainty，由 Agent 在
result.json 中如实声明。

## 4. 数值合法性

- budget、machine_rate、consumable_price 为负 → 拒绝（退出码 3）；
- daily_machine_hours、deadline 必须为正 → 否则拒绝（退出码 3）；
- 方案版本的 runs/hours_per_run/consumables_per_run 为负或缺失 → 该版本拒算；
- 方案版本列表为空 → 输出 status=partial 的空成本表（退出码 0），
  记入 uncertainty，绝不伪造一个"默认方案"。

## 5. 数值语义

- 金额与时间一律使用 Decimal（十进制）语义，不用二进制浮点累乘；
- 输出保留两位小数（ROUND_HALF_UP）；
- 工作日 = ceil(总机时 / 每日可用机时)，向上取整（占用即算一天）；
- 算术痕迹中的中间值原样展示（如 67.50 hour），禁止只给结论数字。
