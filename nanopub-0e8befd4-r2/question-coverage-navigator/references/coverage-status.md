# 覆盖、回答模式与状态规范

## 1. 四种回答模式

| 模式 | 含义 | 必要审计材料 | 禁止 |
|---|---|---|---|
| `direct_report` | 来源直接陈述该答案，可有保持原意的压缩 | 至少一条 `support=direct` 的 evidence，locator + quote | 把自行换算或作者假设写成原文直接值 |
| `computed` | 回答者由已定位输入执行算术、单位换算或重组计算 | 输入 evidence 中至少一条 `support=computed`，完整 `derivation`（公式、输入、单位） | 只有结果没有可复算链；使用来源外的隐藏输入 |
| `inferred` | 回答者结合证据做解释、判断或外推 | 至少一条 `support=inferred`，`rationale` 指明推理与边界 | 把推断语气改成事实；伪造原文结论 |
| `unreported` | 任务要求的信息经定向检索仍未报告/不足 | 非空 `searched_scope`，明确未报告回答，写明不确定性 | 未搜索就称未报告；以“无显著”或 0 冒充未报告 |

每行只选一种主模式。同一行混有两种模式时继续拆子问题。若直接数字被用于计算，则最终答案为 `computed`，可关联直接输入 evidence，但仍需至少一条计算记录。

## 2. 状态及进度硬上限

| `status` | 语义 | `progress_percent` 允许范围 |
|---|---|---|
| `answered` | 回答及链条完整闭合 | 0–100；最终闭合应为 100 |
| `partial` | 只有部分子问题/限定条件闭合 | 0–50 |
| `unanswered` | 尚未取得可回答内容 | 只能为 0 |
| `unreported` | 检索闭合但来源未报告；不是 answered | 0–100；检索闭合时为 100 |

工具验证的是不可突破的上限，不会把 100 当作真实性的替代。所有值必须在 0–100，`confidence` 在 0–1。父问题含未答子问题时不得标记 `answered`；有未报告子问题但其他部分有答案，通常标 `partial`。

`unreported=100` 表示对该缺口的检索流程闭合，不表示问题已有实证答案。最终摘要必须分别统计 answered 与 unreported，不能混成同一成功率。

## 3. ID 与链接规则

- question/subquestion、claim、evidence、source 各自命名空间内不得重复。
- 每个问题的 `claim_ids` 与 `evidence_ids` 必须存在且为数组；未报告行可为空数组，其他叶子行必须非空。
- claim 必须引用至少一个已注册 evidence；evidence 必须引用已注册 source。
- question/subquestion 引用的 claim/evidence 均不得悬空。局部数组内重复引用也应修正。
- claim 文本应是原子、可判真的陈述，不要只写“见上文”。
- 删除断言时同步更新所有父级链接和 result payload；保留 `change_records` 说明原因。

## 4. 覆盖与闭合定义

一个叶子行满足以下条件才算覆盖记录完整：

1. 问题文本与 requirement matrix 非空，预登记证据种类和断言链接。
2. answer 非空并直接回答；`unreported` 的 answer 也必须明确陈述未报告。
3. 回答模式、状态、进度、置信度合法。
4. claim/evidence 链完整，或属于合规 `unreported` 且无伪造实证 claim。
5. sources 记录来源级 uncertainty，change_records 记录实质修改。

完整 coverage JSON 不代表研究已完成。它可以是诚实的 partial：校验器通过表示“可审计、无结构缺口”，不是所有问题都 answered。

## 5. result.json 与 EXACT

`/input/task.md` 中的 `output_contract` 优先于 case、本 Skill 示例和 manifest 默认值。最终 `result.json` 必须含原 `case_id` 和该任务实际声明的全部字段。

当契约为 `EXACT`（或等价 `exact_top_level=true` / `additionalProperties=false`）时，顶层允许集合恰为 `{case_id} ∪ contract fields`：少字段、多字段都失败。契约未要求 EXACT 时，额外字段不因此报错，但缺失仍报错。字段内部结构仍遵循任务语义，不能借 EXACT 删除嵌套必需内容。

保存 partial 时也一样遵守顶层契约：答案元素可处于 unanswered/partial，字段不可随意删除，case_id 不可改。

## 6. 报告解读

`coverage-report.json` 的 `ok=true` 表示本次结构及链接校验通过。`gaps` 是可供 Agent 修复的清单，含错误码、JSON 路径、说明和修复建议。`summary` 分开报告问题、子问题、回答模式及状态数量。失败退出码为 1；无法读取/解析输入等运行错误为 2；成功为 0。

校验器不判断科学结论是否真实，不计算数值答案，不解析 PDF 版面，不导出 RDF，也不能替代领域复核。
