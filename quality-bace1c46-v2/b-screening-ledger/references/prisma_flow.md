# PRISMA-2020 风格流程阶段与算术不变量

本技能按 PRISMA 2020 流程图（identification → screening → included）的语义定义阶段与计数，
由 `scripts/flow_check.py` 自动计算并强制校验。

## 阶段定义

| 阶段 | 字段名 | 含义 |
|---|---|---|
| identified | `identified` | 从所有来源快照收割到的原始记录总数（去重前） |
| duplicates removed | `duplicates_removed` | 去重阶段移除的重复记录数（每条合并记录计入） |
| records screened | `unique_screened` / `screened` | 去重后进入标题/摘要筛选的唯一记录数 / 实际已有有效决定的记录数 |
| records excluded (with reasons) | `excluded` | 标题/摘要阶段被排除的记录数，**每条都必须有 ≥1 条 criterion** |
| reports sought for retrieval | `reports_sought` | 标题/摘要阶段通过、进入全文获取阶段的记录数（= include + uncertain，若任务含全文阶段） |
| reports not retrieved | `reports_not_retrieved` | 无法获得全文的记录数（离线快照环境通常为 0，须显式声明） |
| reports assessed for eligibility | `assessed` | 全文合格性评估的记录数（本技能的 title_abstract 阶段即视为 assessed） |
| included | `included` | 最终纳入的记录数 |

本技能的默认阶段为 `stage=title_abstract`；若任务要求全文阶段，决定行可写
`stage=full_text`，各阶段分别满足下方不变量 2。

## 校验器强制的算术不变量

1. `identified − duplicates_removed = unique_screened`
   （去重只移除记录，不新增；任何对不上都说明收割/去重日志缺失）。
2. 每个阶段：`screened(stage) = include(stage) + exclude(stage) + uncertain(stage)`，
   且 `screened(stage) ≤ unique_screened`。
3. 每条 `exclude` 决定至少携带一条已知 criterion id（C-*）；无 criterion 的排除视为
   不变量违反。
4. 每条被采用决定的 `evidence_quote` 均已通过 apply_decisions.py 的子串核验
   （flow_check 信任 screening.jsonl，因为未过核验的行根本进不来）。
5. 同一 cand_id 多条决定时最后一行生效；历史不删除。

任一不变量不满足：`flow_check.py` 退出码 1，`flow.json` 的 `invariants` 中标出失败项，
必须修复后重跑，不得带着被破坏的计数交付。

## 遗漏声明（omission statements）怎么写

遗漏声明不是失败，而是**诚实边界**。flow_check.py 自动生成，写进 `flow.json` /
`flow_report.md` / `result.json.omissions`：

- **未筛选列表**："以下 N 条候选尚无有效筛选决定：C007, C013, …（原因：预算/时间限制，
  见 uncertainties）"。
- **待定列表**："以下 N 条候选因元数据不足判为 uncertain，待全文或补充元数据后复筛：
  C004（缺摘要），…"。
- **零结果声明**（两种情形）：
  - 空候选集："本次离线快照中检索到 0 条候选记录。可能原因：快照覆盖范围、键名未被
    识别（见 harvest_report.notes）。已执行完整流水线，无候选被发明。"
  - 筛选后无纳入："经筛选无符合全部纳入标准的文献（n 条排除均附理由与证据引句，
    见 screening）。"

书写要求：用陈述句、给出具体数字与 cand_id 列表、指向可核查的文件位置；禁止用
“基本覆盖”“大部分完成”之类含糊措辞替代清单。
