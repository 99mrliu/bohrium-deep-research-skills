# 指标定义（metrics-definition）

`metrics.py` 计算的全部指标在此定义。记号：

- `R` = 待检 result.json 的 `new_items` 条目集合，`n = |R|`
- `E` = 期望新增集合：对 case.json `materials.sources` 列出的每个源题录响应，
  取发表/入库日期落在窗口内、且 DOI 不在 previous_snapshot 中的记录之 DOI 集合
- `V ⊆ R` = 通过全部已运行门禁（evidence_spotcheck 与 freshness_check 无 fail 检查）
  的条目集合
- 所有比率 ∈ [0, 1]；不可计算时输出 `null` 并在 notes 说明（诚实 unknown）

## 1. window_coverage（窗口覆盖率，宽松口径）

```
window_coverage = | { doi(r) : r ∈ R } ∩ E | / |E|
```

按 DOI 计：期望新增记录中有多少出现在 result 中（无论该条目本身是否通过门禁）。
用于发现**漏报**。

## 2. window_coverage_strict（窗口覆盖率，严格口径）

```
window_coverage_strict = | { doi(r) : r ∈ V } ∩ E | / |E|
```

仅统计通过全部门禁的条目。宽松与严格口径之差反映"覆盖了但证据/新鲜度有问题"的
条目数量。未提供子门禁报告时为 null。

## 3. dedup_rate（去重失败率）

```
dedup_rate = ( 内部重复条数 + 与 previous_snapshot 重叠条数 ) / n
```

- 内部重复：同一归一化 DOI 在 `new_items` 中出现 k 次，计 k−1 条；
- 快照重叠：DOI 出现在 previous_snapshot 中的条目数。

理想值为 0；> 0 说明增量判定或去重环节失效（旧文重报 / 自我重复）。

## 4. alert_precision（提醒精确率）

```
alert_precision = |V| / n
```

产出的提醒中"确属本窗口真实新增且证据可回溯"的比例。这是对照 evidence（源题录）
与 freshness（窗口 + 快照 + 投递记录）两个门禁的综合判定，等价于"对照期刊关注
列表/投递记录核实后，有效提醒 / 全部提醒"。未提供子门禁报告时为 null。

## 5. quarantine_rate（隔离率）

```
quarantine_rate = |R \ V| / n = 1 − alert_precision
```

被任一质量门禁判 fail 而应隔离（quarantine）的条目比例。隔离条目不得进入交付版
result.json 的 new_items；若业务要求保留，必须移入单独的 quarantined 列表并附原因。

## 6. locator_resolvability（locator 可解析率）

```
locator_resolvability = locator 检查 pass 的条目数 / 有 locator 检查的条目数
```

来自 evidence_spotcheck 报告。理想值为 1；< 1 说明存在无法回溯复核的断言，
违背"任何字段值必须可经 locator 复核"的平台契约。无 spotcheck 报告时为 null。

## 7. delivery_consistency（投递一致性，可选）

```
delivery_consistency = | { doi(r) : r ∈ R } ∩ delivered(D) | / n
```

对照 case.json `materials.delivery_log` 的 `delivered` 列表：result 声称的条目
有多少实际投递过。用于发现"声称新增但从未投递"或"投递了但未入 result"的记录
不一致。无投递记录时为 null。

## 解释准则

- 指标是**诊断**而非门禁：metrics.py 永远退出码 0；判定由 qa_report 依据
  各门禁 pass/fail 做出；
- 覆盖率 < 1 → 漏报；精确率 < 1 → 误报/证据不足；dedup_rate > 0 → 去重失效；
  locator 可解析率 < 1 → 可复核性破坏。所有非理想值都必须在 result.uncertainty
  与 qa_report 中如实解释；
- 指标计算只读取案例材料与门禁报告，不引入任何外部数据。
