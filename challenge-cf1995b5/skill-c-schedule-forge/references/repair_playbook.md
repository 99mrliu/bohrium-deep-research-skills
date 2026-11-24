# 超期修复策略库（repair playbook）

超期（schedule `overrun_days > 0` 或 throughput 瓶颈天数 > deadline）时，按本库顺序评估。
通用原则：**只有作用于瓶颈设备、且不在并行掩蔽下的压缩才等额缩短总工期**；
每采纳一项必须改写步骤表并重跑 schedule 验证（repair 的 saved_days 是设备级折算）。

## 策略 A：提高并行批次
- 触发：步骤 `samples > 1`、`parallel: false`、提供 `per_sample_hours` 与 `batch_capacity`。
- 算式：`节省机时 = samples×per_sample_hours − ceil(samples/batch_capacity)×per_sample_hours`；
  `节省天 ≈ floor(节省机时 ÷ 该设备每周机时 × 7)`。
- 代价：批内均一性风险（温度场/气氛梯度）；需确认设备批量夹具/载台（confirmation_items）。
- 适用优先级：瓶颈设备上的多样本步骤首选。

## 策略 B：合并表征批次
- 触发：≥2 个步骤同 `equipment` 且同 `batch_group`。
- 算式：`单独 slot 数 = Σ ceil(h_i/slot_hours)`；`合并 slot 数 = ceil(Σh_i/slot_hours)`；
  `节省机时 = (单独 − 合并) × slot_hours`。
- 代价：样本需等同批齐样，表征时效性下降；跨条件同批需防交叉污染/串样。
- 注意：对表征类设备（XRD/SEM）效果好；对已是连续占满的设备收益为零。

## 策略 C：削减重复次数
- 触发：步骤 `replicates > 1`。
- 算式：`单次机时 = equip_hours ÷ replicates`；减 1 次重复即省单次机时。
- 代价：统计功效下降——n=2 无法稳健估计方差；建议底线 n≥3，
  或改"分批重复"（首批全条件 n=2，显著条件补 n=3）。
- 红线：关键结论步骤不得削减到无重复；被削减的步骤在 plan.md 注明统计风险。

## 策略 D：改用可替代设备
- 触发：步骤声明 `alt_equipment`，且替代设备在合同设备表内、当周有空闲 slot。
- 算式：`瓶颈设备释放天数 ≈ floor(equip_hours ÷ 瓶颈每周机时 × 7)`；
  实际收益取决于替代设备自身的 slot 占用，必须重排验证。
- 代价：机时单价差（可正可负）；两设备结果可能有系统偏差，
  需在 plan.md 注明口径差异并考虑留 1 组交叉验证样本。
- 替代设备不在合同表 → 该选项不可用（repair 标记 unavailable），进 confirmation_items。

## 组合与迭代
1. 第一轮：对瓶颈设备选 saved_days 最大且代价可接受的 1–2 项，重排；
2. 第二轮：瓶颈可能转移到另一台设备——重新读 schedule 的 weekly_usage 找新瓶颈；
3. 第三轮仍超期：停止压缩，交付 honest partial：
   报告最小可达工期、剩余缺口天数、以及"若 window 可续约/若预算可加"的条件式方案
   （全部进 confirmation_items，不得写成可执行事实）。
4. 全程检查副作用：压缩不能引入新双订、不能让现金流超 budget_cap、
   不能把参数推出 parameter_domains。
