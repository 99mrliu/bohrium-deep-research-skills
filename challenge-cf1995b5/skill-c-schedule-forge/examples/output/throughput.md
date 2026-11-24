# throughput 体检报告
case_id: MOCK-GARP-001    deadline: 30.0 天
合同声明: 组织方前瞻合同：价格与预约信息为计划性约定，不是实际供应商报价或已确认排期。

- 合并说明: 从 equipment_domain_note 解析出补充设备 EQ-HP（精密加热台），已并入设备表。

## 设备吞吐表
- EQ-GB 充氮手套箱: 3 slots/周 × 4 h = 12.0 h/周；window 30 天 = 4 完整周 → 48.0 h（来源: resource_contract.equipment）
- EQ-HP 精密加热台: 7 slots/周 × 2 h = 14.0 h/周；window 30 天 = 4 完整周 → 56.0 h（来源: equipment_domain_note(内嵌JSON片段)）
- EQ-XRD X 射线衍射仪: 5 slots/周 × 2 h = 10.0 h/周；window 30 天 = 4 完整周 → 40.0 h（来源: resource_contract.equipment）

## 候选 v1（est_days=28）
- EQ-GB: 需求 40.0h ÷ 每周 12.0h（3 slots/周 × 4.0h/slot） = 4 周 = 28 天  ✅ window 内可容纳
- EQ-HP: 需求 20.0h ÷ 每周 14.0h（7 slots/周 × 2.0h/slot） = 2 周 = 14 天  ✅ window 内可容纳
- EQ-XRD: 需求 15.0h ÷ 每周 10.0h（5 slots/周 × 2.0h/slot） = 2 周 = 14 天  ✅ window 内可容纳
- 瓶颈设备: EQ-GB（28 天）；deadline 30.0 天 → 未超期
- est_days 判定: est_days 不低于瓶颈下界且未超 deadline（但仍需 schedule 做全资源联检）
- 算术问题: 「XRD」subtotal 算术错误：120.0×15.0=1800.0 ≠ 声明 1500.0
- 算术问题: total_cost 算术错误：Σsubtotal=8000.0 ≠ 声明 total_cost=7330.0
- 假设: cost_item「手套箱」按 unit_price=80.0 匹配到设备 EQ-GB，quantity=40.0 视为机时小时数（假设）。
- 假设: cost_item「加热台」按 unit_price=40.0 匹配到设备 EQ-HP，quantity=20.0 视为机时小时数（假设）。
- 假设: cost_item「XRD」按 unit_price=120.0 匹配到设备 EQ-XRD，quantity=15.0 视为机时小时数（假设）。

## 候选 v2（est_days=21）
- EQ-GB: 需求 96.0h ÷ 每周 12.0h（3 slots/周 × 4.0h/slot） = 8 周 = 56 天  ❌ 超出 window 总机时
- EQ-XRD: 需求 20.0h ÷ 每周 10.0h（5 slots/周 × 2.0h/slot） = 2 周 = 14 天  ✅ window 内可容纳
- 瓶颈设备: EQ-GB（56 天）；deadline 30.0 天 → 超期 26.0 天
- est_days 判定: est_days 低于瓶颈机时所需天数，不可信
- 假设: cost_item「手套箱」按 unit_price=80.0 匹配到设备 EQ-GB，quantity=96.0 视为机时小时数（假设）。
- 假设: cost_item「XRD」按 unit_price=120.0 匹配到设备 EQ-XRD，quantity=20.0 视为机时小时数（假设）。

## 候选 v3（est_days=35）
- EQ-GB: 需求 60.0h ÷ 每周 12.0h（3 slots/周 × 4.0h/slot） = 5 周 = 35 天  ❌ 超出 window 总机时
- EQ-XRD: 需求 25.0h ÷ 每周 10.0h（5 slots/周 × 2.0h/slot） = 3 周 = 21 天  ✅ window 内可容纳
- 瓶颈设备: EQ-GB（35 天）；deadline 30.0 天 → 超期 5.0 天
- est_days 判定: est_days 超过 deadline
- 假设: cost_item「手套箱」按 unit_price=80.0 匹配到设备 EQ-GB，quantity=60.0 视为机时小时数（假设）。
- 假设: cost_item「XRD」按 unit_price=120.0 匹配到设备 EQ-XRD，quantity=25.0 视为机时小时数（假设）。

## 用户方案 rev1（/Users/liuhengshen/Desktop/bhr_product/3rd/4/submit/skills-cf1995b5/skill-c-schedule-forge/examples/plan_revised.json）
- EQ-GB: 需求 56.0h ÷ 每周 12.0h（3 slots/周 × 4.0h/slot） = 5 周 = 35 天
- EQ-HP: 需求 16.0h ÷ 每周 14.0h（7 slots/周 × 2.0h/slot） = 2 周 = 14 天
- EQ-XRD: 需求 10.0h ÷ 每周 10.0h（5 slots/周 × 2.0h/slot） = 1 周 = 7 天
- 瓶颈: EQ-GB 35 天，超期 5.0 天
