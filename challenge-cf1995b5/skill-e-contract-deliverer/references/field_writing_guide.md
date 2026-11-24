# 字段写作要点与反例

## revised_plan

要点：
- 六要素齐全：假设与变量、对照组、设备与材料、时间与成本、参数范围、风险与异常。
- `parameters` 用 dict：键名与 case.json `parameter_domains` 对齐，值必须在域内
  （range 看 min/max/step，enum 看 values）。需要扫描多个水平时用数组，每个元素都要在域内。
- 成本以 `plan.json` 的 cost_items 为准，revised_plan 里引用总额即可，两处数字必须一致。
- 每个数字标来源：case.json 路径或"假设"。

反例：
```json
{"revised_plan": "按文献最佳条件退火即可，温度 160°C 保温。"}
```
问题：无六要素、无 parameters dict、160°C 越出域上限 150、无来源、无对照。

正例骨架：
```json
{"revised_plan": {
  "hypothesis": "……（假设）",
  "variables": {"independent": ["anneal_temperature_C"], "dependent": ["薄膜覆盖率/PL 强度"]},
  "controls": ["未退火对照", "candidate v1 的 125°C 单点对照"],
  "equipment_materials": [{"id": "EQ-GB", "source": "resource_contract.equipment[0]"}],
  "schedule": {"est_days": 24, "basis": "slots_per_week=3 × slot_hours=4h，见 validation"},
  "parameters": {"anneal_temperature_C": [100, 110, 120], "spin_coating_rpm": 4000},
  "risks": ["手套箱预约冲突 → 提前 7 天锁档"]}}
```

## candidate_assessment

要点：一个候选一条评估，每条至少跑三项机械对账：
1. 成本算术：`sum(unit_price*quantity)` 对比 `total_cost`；
2. 时间吞吐：`est_days` 对比 `deadline_days` 与 booking（window_days × slots_per_week × slot_hours）；
3. 参数域：parameters 逐项对 parameter_domains；
外加：equipment_domain_note 内嵌设备是否出现在 equipment 列表（对账，不是肉眼跳过）。

反例：`"v1/v2/v3 各有优劣，综合选 v1"`——没有一条可复算的证据。

## validation

要点：写成"检查项 → 方法 → 数据 → 结论"的列表，与 validate 子命令输出的
validation_report.json 呼应；引用脚本结论时注明是脚本机械复核过还是自己复算的。

反例：`"所有数据已仔细核对无误"`——无检查项、无数据、不可复算。

## confirmation_items

要点：凡属"组织方前瞻合同"（价格、预约窗口、pack_size 余量）、任何未书面确认的信息、
以及"想越域做"的参数意图，都进这里；措辞用"需确认"，不用"已确认/将"。

反例：把 `price_per_hour=80` 写成"手套箱时租 80 元（已与供应商确认）"——
case 明确 disclaimer 为前瞻约定，这是科学诚实红线。

## uncertainty

要点：假设、估计误差、工具降级（如"未生成 PDF 预览：环境无 pandoc/libreoffice"）都如实写。
render 子命令会自动追加 PDF 降级原因，不要删掉它。
