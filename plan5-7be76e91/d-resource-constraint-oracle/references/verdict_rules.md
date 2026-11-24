# verdict 判据与 blocking / warning 规则

本文件是 `constraints.py` 裁决规则的说明文档，供模型解读报告与撰写 result.json 时引用。

## 三档 verdict

| verdict | 判据 | 含义 |
| --- | --- | --- |
| `feasible_now` | 无任何 blocking 违例，且 start_bound ≤ 基准日 | **本实验室现在可做**：设备有空档、耗材现货/已到货、审批齐备、技能覆盖。 |
| `feasible_after(YYYY-MM-DD)` | 无 blocking 违例，但 start_bound > 基准日 | 理论上与资源上都可做，但要等到给定日期：该日期 = 所有启动约束（设备首个足够长空档起点、耗材到货日、pending 审批预计获批日）的**最大者**。 |
| `infeasible` | 存在任一 blocking 违例 | 在现状约束下不可做；必须满足 relax_hints 中的解除条件之一后才可重评。 |

start_bound 由脚本逐约束取最大算出，模型不得自行改写；撰写结论时应区分
「理论上可行」（参数窗口与设备能力相容、文献支持）与「本实验室现在可做」
（feasible_now / feasible_after 且排期不超 deadline）。

## blocking（阻断，出现即 infeasible）

| type | 触发 | 解除方向（relax_hints 展开） |
| --- | --- | --- |
| equipment_missing | 需求设备不在资源清单 | 购置/租用/外协或改方案 |
| equipment_unavailable | 设备 available=false | 等恢复或替代设备 |
| equipment_capability_missing | 设备未声明所需能力项 | 查设备手册补核，或更换设备 |
| equipment_capability_insufficient | 设备能力窗口不覆盖需求窗口 | 收缩需求窗口或更换设备 |
| equipment_booking_conflict | 需求窗口内无 ≥duration 的连续空档 | 协商档期/顺延窗口/替代设备 |
| equipment_window_malformed | earliest_use ≥ latest_use | 修正方案需求窗口 |
| consumable_missing | 需求耗材不在清单 | 补渠道或替代料 |
| consumable_not_obtainable | 无现货且不可订购 | 找渠道或替代料 |
| consumable_lead_time_exceeded | 到货日 > needed_by | 现货供应商/顺延截止（需批准） |
| budget_exceeded | 方案耗材总价 > 预算 | 增预算/议价/替代料 |
| parameter_window_conflict | 方案窗口 ⊄ 设备极限 ∩ 契约域（含空交集） | 收缩/平移窗口；或向契约方申请放宽参数域 |
| skill_missing | 技能要求 ⊄ 人员技能集 | 培训/外聘 |
| approval_missing / approval_blocked | 审批无记录或未获批（rejected/not_started） | 补办/重新申报并获批 |

## warning / notes（不阻断，但影响 feasible_after 或需写入确认项）

- 设备首个空档晚于基准日 → 构成启动约束（写入 notes，抬高 start_bound）。
- 耗材有货期、审批 pending 有预计日期 → 同上。
- 审批 pending 但无预计日期 → notes 提示，必须写入 result.json 的确认项。
- 参数无设备极限与契约域约束（unbounded）→ notes 提示，列入假设。

## 退出码约定

- constraints.py：任一方案 feasible_now/feasible_after → 0；全部 infeasible → 3 且输出 relax_hints。
- window_check.py：无空交集 → 0；存在空交集 → 3（交集矩阵仍写出）。
- timeline.py：至少一个方案排出 → 0；无可排方案（或全部被 constraints 跳过）→ 3。
- 所有脚本：输入/用法错误 → 2。
