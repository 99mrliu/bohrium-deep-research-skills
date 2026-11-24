# 时间口径模型（time_model.md）

本文件定义 `time_model.py` 的口径。核心区分：**labor_hours（人力工时）**
与 **elapsed_days（自然周期）** 是两个不同量纲的账，不可混加。

## 1. 六阶段（phase）

| phase | 中文 | 计入 labor_hours | 计入 elapsed |
|---|---|---|---|
| sample_prep | 样品准备 | 是 | 是 |
| booking_wait | 设备排期等待 | **否** | 是 |
| execution | 实验执行 | 是 | 是 |
| characterization_queue | 表征排队 | **否** | 是 |
| analysis | 数据分析 | 是 | 是 |
| rework_buffer | 返工缓冲 | 是 | 是 |

**失败模式对应**：题目点名"时间只算实验执行，不算样品准备、设备排期、表征
排队和返工"。脚本强制逐条枚举 phase，排期/排队只进自然周期、不冒充人力
工时；若把排队当 labor 会虚增人力成本，若把排队从 elapsed 删掉会漏掉截止
风险——两者都是机检项。

## 2. 单位换算

- `unit` 只允许 `hours` | `days`。
- 换算 `1 day = workday_hours 小时`，`workday_hours` 必须在 plan_record 顶层
  或 case.json 中显式给定（plan 优先，并记录 `workday_hours_source`）。
- **缺省报错 exit 2，绝不臆造 8 或 24**。契约若写的是"自然日"，应由模型在
  抽取时把 workday_hours 设为 24 并注明依据。
- `labor_hours` 以小时报告；`elapsed_days = elapsed_hours / workday_hours`。

## 3. 返工期望

- `expected_rework = rework_probability × rework_cost`，计入该条目所属 phase
  的小时数（labor 与 elapsed 同步加）。
- `rework_probability` 必须在 `[0,1]`，越界（如 1.4）→ 缺陷 exit 3。
- 给了 `rework_probability` 缺 `rework_cost`（或反之）→ 缺陷 exit 3。
- `rework_cost` 的单位与该条目 `unit` 相同（条目 unit=days 时 rework_cost=1
  表示返工一次耗 1 个 workday）。

## 4. 硬约束门（gate）

从 case.json 读（均为可选键）：

- `budget`：总成本上限。判定需要 cost_ledger 的 grand_total，因此必须传
  `--ledger`；case 有 budget 却没给 --ledger → exit 2（无法判定，不猜）。
  `total_cost > budget` → `over_budget`。
- `deadline_days`：自然周期上限。`elapsed_days > deadline_days` → `past_deadline`。

`gate_status` = `pass` | `over_budget` | `past_deadline` |
`over_budget+past_deadline`。任一触发 → exit 3，报告（含逐阶段台账与门明细）
仍完整写出，供模型在 result.json 中诚实上报。

## 5. 输出字段

`time_<plan_id>.json/md`：逐条目台账（phase/时长/折算小时/期望返工/计入口径/
来源）、逐阶段合计（含其中计人力的部分）、labor_hours、elapsed_hours、
elapsed_days、gates 明细、gate_status、defects。
