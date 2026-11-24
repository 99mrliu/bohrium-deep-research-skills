# 排期模型假设（scheduling model）

本文件定义 exp-schedule-forge 的排程语义。任何由脚本产出的数字都以下列假设为前提；假设不成立时结论降级为 partial。

## 1. 时间粒度：一周 7 天计
- 不做节假日/周末建模：1 周 = 7 个日历日，第 w 周 = 开工日 + 7×(w−1) 起的 7 天。
- `window_days` 折算完整周数：`weeks = floor(window_days / 7)`（保守，余数天不计入可用机时）。
  例：window_days=30 → 4 周。设备在窗口内的总可用机时 = 每周机时 × 4。
- 步骤工期以"占用的最后一个 slot 所在周"结算；总工期 = 最后周序号 × 7 天。

## 2. slot 粒度
- 每台设备每周提供 `slots_per_week` 个 slot，每 slot 固定 `slot_hours` 小时；
  每周可用机时 = `slots_per_week × slot_hours`。
- 步骤机时 `equip_hours` 向上取整为 slot 数：`ceil(equip_hours / slot_hours)`——
  不满一个 slot 也占一个 slot（上机准备/清场成本并入 slot）。
- slot 是设备级互斥资源：同一设备同一周占用 slot 数不得超过 `slots_per_week`，
  脚本在排程后对每设备每周做双订不变量校验（占用 ≤ 上限）。

## 3. 依赖与并行规则
- `depends_on` 为**严格先后**：被依赖步骤占用的最后位置 (week, slot_index) 之后，
  依赖步骤才能开始；允许在同一周靠后的 slot 继续（跨设备亦同，属保守近似：
  不同设备的 slot 序号被当作同一周内的先后序，可能高估 0–1 周，绝不低估）。
- 同一设备上的多个步骤按拓扑序先到先得地占用 slot。
- `parallel: true` 仅声明该步骤**可批处理**（配合 `per_sample_hours` 与
  `batch_capacity` 供 repair 计算并行化收益）；排程器始终以步骤表中的
  `equip_hours` 为准——采纳批处理必须改写 `equip_hours` 后重排。
- 零机时步骤（equip_hours=0，如纯记录/审批）不占 slot，跟随依赖位置。
- `prep_days`（如样品老化等待）按 `ceil(prep_days/7)` 整周顺延开始周。

## 4. 可行性判定层级
1. **throughput（必要非充分）**：每台设备独立核算 `需求机时 ÷ 每周机时 = 周数`，
   瓶颈设备周数 × 7 天 ≤ deadline 才可能可行；任一设备需求 > 窗口总机时必不可行。
2. **schedule（充分判定）**：全资源联合排程后总工期 ≤ deadline 才算排得下，
   同时检测依赖冲突、window 溢出、设备双订。
3. **est_days 可信判定**：`est_days < 瓶颈天数` → 不可信（拍脑袋）；
   `est_days > deadline` → 方案本身违约；通过 throughput 的仍需 schedule 联检。

## 5. 现金流模型
- 设备成本：步骤结束后当周结算 `slots × slot_hours × price_per_hour`。
- 试剂成本：按 `ceil(需求量 / pack_size)` 整包采购，首次使用前
  `reagent_lead_weeks` 周（默认 1）计入支出。
- 按周累计并与 `budget_cap` 比较；超预算周在 cashflow.md 标 ❌。

## 6. 六要素交付清单（方案完整性，不只排期）
| 要素 | 落点 |
|---|---|
| 假设与变量 | 每步 equip_hours/samples 的来源标注（case 路径或"假设"） |
| 对照组 | 对照步骤同样占 slot、进 depends_on 图 |
| 设备材料 | 仅合同设备表（含 note 解析合并）与 reagents 列表内的条目 |
| 时间成本 | gantt.md + cashflow.md + throughput 算式 |
| 参数范围 | 步骤参数逐项对照 parameter_domains（range/enum） |
| 风险和异常 | repair 选项代价列 + SKILL.md 失败模式表 + confirmation_items |
