# output_contract 字段映射与 null 策略（contract mapping）

## 1. 映射表（contract_probe.py 内置）

契约字段名不区分大小写按下表归并；同一字段名出现在契约里时按原名镜像回 result.json。

| 契约字段（别名） | 来源产物 | 说明 |
|-|-|-|
| research_product / product / review / draft | work/review_draft.md + work/themes.json | 草稿全文、主题结构、底线结论 |
| evidence_matrix / evidence / ledger / matrix | work/evidence_ledger.jsonl | 证据行（逐字摘录 + 锚点 + strength） |
| screening_log / screening | work/screening_log.json | 纳入/排除标准与逐篇决定 |
| uncertainties / uncertainty | work/uncertainties.json + 各阶段汇总 | 降级、异常、null 说明全部汇入 |
| sources / source | work/docs.jsonl + work/run_plan.json | doc_id、sha256、tier、阅读深度 |
| change_log / changes | work/change_log.json | budget_ledger mark 自动维护 |
| run_plan / plan | work/run_plan.json | 预算分配与阅读计划 |
| consistency_report / consistency | out/consistency_report.json | 最近一次一致性校验 |
| requirements | work/requirements.md | task.md 硬性要求清单 |
| case_id | work/case_profile.json | 防御式探测结果 |
| status | build_result.py 裁定 | completed / partial / blocked |

未命中上表的契约字段：`contract_map.json` 标 `unmapped_fields`，result.json 中
**填 null 并保留字段**，同时在 uncertainties 写明"无对应内容"。

## 2. null 策略（三条铁律）

1. **null 是合法占位，漏字段不是。** result.json 必须含 output_contract 全部字段；
   consistency_check 对缺失字段判失败，对 null 字段按 status 区分：
   in_progress 时记 pending（正常中间态），终态时判失败并要求 uncertainties 说明。
2. **null 必须带原因。** 每个终态 null 字段在 uncertainties 有一条对应说明
   （产物缺失的原因：阶段被降级裁掉 / 源材料不足 / 解析失败等），禁止裸 null。
3. **不得以编造填充。** 宁可 null + 说明，不得用模型臆造内容填契约字段；
   契约字段的内容必须能回链到 contract_map.json 声明的来源产物。

## 3. partial result.json 的生命周期

- init 时由 contract_probe 写出：case_id + status=in_progress + 全部契约字段 null。
- 模型阶段进行中：保持不变，作为中断兜底。
- finalize 时由 build_result 重建：真实内容替换 null，status 改为
  completed/partial/blocked；blocked 时契约字段仍全部在场（多为 null + 说明）。
