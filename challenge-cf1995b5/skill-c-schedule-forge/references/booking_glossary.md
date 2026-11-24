# 预约合同字段语义与前瞻性质声明模板

## 1. resource_contract 字段语义
| 字段 | 含义 | 排期含义 |
|---|---|---|
| `equipment[].id` / `name` | 设备标识 | 步骤表 `equipment` 必须命中此 id（含 note 解析合并的） |
| `price_per_hour` | 机时单价（元/h，前瞻约定价） | 现金流与成本核算单价；非实际报价 |
| `booking.window_days` | 可预约窗口（天） | 折算 `floor(window_days/7)` 个完整周的可用机时 |
| `booking.slots_per_week` | 每周可约 slot 数 | 设备级周并发上限 |
| `booking.slot_hours` | 每 slot 小时数 | 步骤机时向上取整到 slot 的粒度 |
| `reagents[].unit_price/pack_size/unit` | 试剂单价/包装规格 | 整包采购 `ceil(需求/pack_size)` |
| `budget_cap` / `deadline_days` | 预算上限 / 截止天数 | 现金流红线 / 排期红线 |
| `disclaimer` | 组织方前瞻声明 | 必须原样传递到交付物 |

## 2. equipment_domain_note 解析规则
- 设备信息可能以**文本内嵌 JSON 片段**出现（如 `{"id": "EQ-HP", ...}`），
  脚本用大括号配平 + JSON 解析提取，合并入设备表并在 `merge_notes` 记录来源；
- 与 `equipment` 列表同 id 时以 `equipment` 列表为准；
- 步骤引用既不在列表也不在 note 的设备 → `unknown_equipment`，**不得假设可预约**。

## 3. 候选方案机时反推（throughput 对 candidate_plans）
- 候选无步骤表，脚本按 `cost_items` 反推：
  显式 `equipment` 字段优先；否则 `unit_price == price_per_hour` 唯一匹配设备，
  `quantity` 视为机时小时数；
- 该反推是**假设**，每条都写入 `assumptions`，交付时必须保留此标注；
- 匹配不上的 cost_item（如试剂）列入 `unmatched_cost_items`，不参与机时核算。

## 4. 步骤表（plan.json steps）字段语义
| 字段 | 类型 | 语义 |
|---|---|---|
| `id` / `name` | str | 步骤标识；depends_on 引用 id |
| `equipment` | str | 设备 id（合同设备表内） |
| `equip_hours` | num | 总机时（排程权威值，向上取整到 slot） |
| `samples` | int | 样本数 |
| `depends_on` | list | 前置步骤 id（严格先后） |
| `parallel` | bool | 是否可批处理（repair 依据） |
| `per_sample_hours` / `batch_capacity` | num/int | 单样机时 / 一批可容纳样本数（repair 计算批处理收益） |
| `replicates` | int | 重复次数（repair"削减重复"依据；equip_hours 视为全部重复的总机时） |
| `batch_group` | str | 同组同设备步骤可合并上机（repair"合并表征批次"依据） |
| `alt_equipment` | list | 可替代设备 id（repair"改用可替代设备"依据） |
| `reagents` | list | `{id, quantity}`，现金流整包采购 |
| `prep_days` | int | 开始前等待天数（按整周顺延） |

## 5. 前瞻性质声明模板（复制进 plan.md / result.json）
> 本方案中的设备机时单价、slots_per_week、slot_hours、window_days 与试剂价格
> 均来自组织方前瞻合同（resource_contract），属于计划性约定，**不是实际供应商
> 报价，也不是已确认排期**。排期结果表示"在该约定吞吐下可排下"，正式执行前
> 需向设备管理方确认：① 实际可约 slot；② 批量夹具/载台；③ 窗口续约可能性；
> ④ 替代设备口径一致性。上述未确认项已列入 confirmation_items。

## 6. confirmation_items 收录标准
- 任何"脚本算出可行但依赖未证实前提"的条目：批处理夹具、替代设备、窗口续约、
  前瞻价格有效性、机时反推假设；
- 写法：每条含 `事项 / 影响 / 建议确认渠道`，不得写成可执行事实。
