# requirements.json 模式与抽取诚实规则

模型对每个方案版本抽取一份 `requirements_<version>.json`，作为后续确定性脚本的
唯一输入。字段名固定如下（脚本按此读取）；值必须来自 case.json / task.md 原文。

## 顶层结构

```json
{
  "case_id": "与 case.json 一致",
  "plan_version": "v1",
  "equipment":  [ ... ],
  "materials":  [ ... ],
  "samples":    [ ... ],
  "booking_needs": [ ... ]
}
```

## equipment 条目

```json
{
  "id": "eq-01",
  "name": "设备名（按原文）",
  "raw_name": "原文中的原始写法（可选）",
  "specs": {"max_rpm": 20000, "min_temperature_c": null},
  "needed_window": {"start": "2026-03-05", "end": "2026-03-06"},
  "gating": true,
  "locator": "task.md §3.1"
}
```

- `specs`：只放原文明确给出的规格。**未知规格 = null，绝不猜测**；
  规格键名用 snake_case（如 max_rpm / max_flow_ml_min / min_temperature_c / channels）。
- `gating`：该资源缺失是否使实验目的无法达成（关键工序 = true）。

## materials 条目

```json
{
  "id": "mat-01", "name": "试剂/耗材名", "quantity": 100, "unit": "mL",
  "needed_by": "2026-03-08", "gating": true, "locator": "task.md §3.3"
}
```

`needed_by` 用于货期核验（order_by + lead_time_days ≤ needed_by）。外协服务
（如测序）也放在 materials 中，用 name 与外协合同的 service 对应。

## samples 条目

```json
{
  "id": "sam-01", "name": "人血清样本", "quantity": 3, "unit": "mL",
  "storage": "-80°C", "source": "附属医院合作",
  "needs_ethics": true, "gating": true, "locator": "task.md §2.2"
}
```

`storage` 用原文写法（如 "-80°C"、"4°C"、"液氮"）。`needs_ethics` 或台账带
ethics_status 字段即触发伦理状态核验。

## booking_needs 条目

```json
{
  "id": "bk-01", "resource": "蛋白纯化系统",
  "start": "2026-03-12", "end": "2026-03-15",
  "gating": true, "locator": "task.md §3.3 排期表"
}
```

优先 ISO 绝对日期；原文只有相对天数时用 `start_day`/`end_day`（整数），由
check_booking.py 用案例基准日换算；两者都缺 → 该项 无法核验。

## locator 约定

`locator` 指向需求出处，格式自由但须可回查，如 `task.md §3.1`、
`case.json $.plans[0].steps[2]`。**每一条需求都必须有 locator**；抽取时不得
加入原文不存在的资源需求（宁缺毋滥，缺了会被脚本判为证据不足而不是编造通过）。

## 抽取诚实规则（硬性）

1. 型号、规格数值、数量、日期一律逐字照抄原文，不四舍五入、不"合理推测"。
2. 原文没有的字段 = null（或不写），禁止用领域常识补全。
3. 原文表述含糊（如"高速离心"无转速）→ specs 留空/null，由脚本判 无法核验，
   并在最终 uncertainty 中说明。
4. 抽取结果只是中间产物：最终结论以脚本输出为准，模型不得绕过脚本直接分类。
