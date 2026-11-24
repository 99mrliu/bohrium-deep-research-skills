# 评分量规与自查项映射（rubric）

> 本量规把赛题常见评分维度（任务完成度 / 结果正确性 / 结果完整性 / 结果可核验性 /
> 可靠性）转成 10 条 yes/no 自查项。其中 5 条可由 `gate.py selfcheck` 机器判定，
> 其余 5 条必须由模型诚实自答，禁止默认全勾。

## 维度 → 自查项

| 编号 | 评分维度 | 自查项（yes/no） | 判定方式 | 机器判定逻辑 |
|---|---|---|---|---|
| Q1 | 任务完成度 | 是否产出了 task.md 要求的全部交付物？ | 模型自答 | — |
| Q2 | 任务完成度 | deliverable 是否逐条覆盖 task.md 的全部要求？ | 模型自答 | — |
| Q3 | 结果正确性 | 每条事实是否都能追溯到具体来源材料？ | 模型自答 | — |
| Q4 | 结果正确性 | 是否存在任何虚构、臆测或未标注的推断？（有为 no） | 模型自答 | — |
| Q5 | 结果完整性 | result.json 是否含 output_contract 全部字段？ | **机器** | 契约键 ⊆ result.json 键 |
| Q6 | 结果完整性 | deliverable 是否非空、≥200 字、无 TODO/XXX 类占位符？ | **机器** | 去空白字数 ≥200 且占位符正则不命中 |
| Q7 | 结果可核验性 | evidence_map 是否非空（结论→证据映射存在）？ | **机器** | evidence_map 为非空 dict/list |
| Q8 | 结果可核验性 | evidence_map 中的来源是否可定位到具体文件/段落？ | 模型自答 | — |
| Q9 | 可靠性 | change_log 是否非空（过程与降级均有记录）？ | **机器** | change_log 为非空 list |
| Q10 | 可靠性 | 不确定处是否均以【待确认】标注并在 uncertainty 中说明？（0 处为 yes） | **机器** | deliverable 中【待确认】计数；>0 时 WARN，需人工确认 uncertainty 已说明 |

## 计分与处置

- 机器项全 PASS 且模型项全部诚实回答 yes：可进入 `deliver`。
- 任一机器项 FAIL：优先修复后重跑 `selfcheck`；预算不足时在 `result.json` 的
  `uncertainty` / `change_log` 如实说明缺口，接受降级交付（`status: "partial"`）。
- 任一模型项回答 no：同上当即修复或如实降级。**本 skill 管流程不管内容**，
  模型自答项是诚实性约束，谎报不会被机器抓住，但违背 skill 的存在意义。
- Q10 的 WARN 语义：【待确认】是合法的不确定性表达，不是缺陷；缺陷是"标了
  【待确认】却不在 uncertainty/change_log 里解释"。
