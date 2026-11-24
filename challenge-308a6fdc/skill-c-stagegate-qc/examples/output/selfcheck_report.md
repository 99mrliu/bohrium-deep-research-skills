# 量规自评报告（selfcheck）

- 生成时间：2026-11-24T11:02:41+00:00；已用时 11s / 900s
- case_id：EXAMPLE-NOT-A-TEST-CASE

## 机器可判定项

| 编号 | 自查项 | 判定 | 说明 |
|---|---|---|---|
| Q5 | result.json 含全部契约字段 | PASS | 5 个字段齐全 |
| Q6 | deliverable 非空且 ≥200 字、无占位符 | PASS | 当前 426 字；占位符：无 |
| Q7 | evidence_map 非空 | PASS | work/evidence_map.json：非空 |
| Q9 | change_log 非空（worklog 已有记录） | PASS | worklog 6 条 |
| Q10 | 【待确认】 标注计数 | FAIL/WARN | 2 处（需在 uncertainty/change_log 说明） |

机器项通过 4/5。

## 需模型自答项（机器无法判定，必须逐条诚实回答）

- [ ] Q1 是否产出了 task.md 要求的全部交付物？
- [ ] Q2 deliverable 是否逐条覆盖 task.md 的要求？
- [ ] Q3 每条事实是否都能追溯到具体来源材料？
- [ ] Q4 是否存在任何虚构、臆测或未标注的推断？
- [ ] Q8 evidence_map 中的来源是否可定位到具体文件/段落？

若任一机器项 FAIL 或模型项答案为否：修复后重跑 selfcheck；无法修复的在 result.json 的 uncertainty/change_log 中如实说明。
