# 方法说明：资源约束裁决如何对应评分点「区分理论上可行与本实验室现在可做」

## 针对的失败模式

题目点名的失败：把文献通用流程整段搬来，不核对本实验室设备是否具备、耗材是否在
预算与货期内；设备档期、耗材货期、场地与安全审批、人员技能与时间窗口不查。
本 bundle 把这类失败变成**可机检的约束满足问题**：

| 失败模式 | 对应机检项 | 脚本 |
| --- | --- | --- |
| 照搬文献流程，不查设备是否存在/能力是否覆盖 | equipment_missing / capability_missing / capability_insufficient | constraints.py |
| 不查设备档期 | equipment_booking_conflict；feasible_after 的日期推导 | constraints.py + timeline.py |
| 不查耗材预算与货期 | budget_exceeded / consumable_lead_time_exceeded / not_obtainable | constraints.py |
| 不查参数窗口冲突（方案 vs 设备极限 vs 契约/文献域） | parameter_window_conflict + 三方交集矩阵 | constraints.py + window_check.py |
| 不查场地与安全审批 | approval_missing / approval_blocked / pending 等待 | constraints.py + timeline.py |
| 不查人员技能与时间窗 | skill_missing；排期时人员可用窗口覆盖检查 | constraints.py + timeline.py |
| 把「理论可行」当「现在可做」 | 三档 verdict + start_bound 日期 + past_deadline 标记 | constraints.py + timeline.py |

## 「理论可行」与「现在可做」的判定链

1. **理论可行性**（必要条件，不充分）：参数窗口三方对照（window_check.py）——
   方案要求窗口必须落在 设备极限 ∩ 契约给定域 内；空交集直接质量门拦截（exit 3）。
2. **现状可行性**（充分条件的现状部分）：constraints.py 逐项查设备/耗材/审批/技能，
   得出 feasible_now / feasible_after(日期) / infeasible(原因)。
3. **排期可行性**：timeline.py 在真实资源日历上串行排期（采购等待→准备→执行→表征排队），
   得出 earliest_start / earliest_finish / 关键等待项，并对超 deadline 标记 past_deadline。
   一个方案可以 feasible_after 但 past_deadline=true —— 这正是「理论上可行、
   本实验室现在赶不上」的情形，必须如实写进 result.json，不得粉饰。

## 分工原则（遵循共同规格）

- **模型**只做判断与文字：读 /input 真实文件，抽取 facts JSON（每条事实挂 source），
  最后依据脚本报告撰写 result.json（七类字段 + 依据与风险 + 确认项）。
- **脚本**做全部确定性工作：区间求交、日期算术、档期扫描、排期、退出码与质量门。
  64 次模型请求 / 900 秒预算内，任何算术都不交给模型。

## 诚实性约束

- 契约是组织方前瞻性给定情景，不是真实实验室/供应商数据：报告中沿用契约口径，
  不得声称「实测」「已询价」。
- 未经确认的建议（如「假设审批会获批」）只能写进确认项，不得写成可执行事实。
- 全部方案不可行时必须诚实报告并给出 relax_hints，不得硬推一个方案。
