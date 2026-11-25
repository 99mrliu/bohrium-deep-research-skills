# Verdict logic and compound-sentence adjudication

本参考中的名称与数据若用于示例均为 **SYNTHETIC / 合成内容，非正式科研结果**。

## 1. 唯一工作对象

输入是已经带有 `input_id` 的科研草稿断言。裁判从原断言开始，逐 ID 对照给定原始源文；不得先把文章重新抽取成另一套断言再做 lint。输入 ID、输入原文和输入顺序信息属于审计证据，不能清洗、润色、合并、拆分后覆盖或静默省略。

`original_claim` 必须与 `case.assertions[].claim` 逐 Unicode 字符相同。可另行提出 `corrected_claims`，但建议文本绝不能回写 `original_claim` 或 `/input/case.json`。

## 2. 先拆 component，再定顶层 verdict

每个 `component` 都是单一、可独立核验的原子命题。一个 component 不得再含“并且”“同时”“以及”连接的两个可分离命题。每个原子 component 只能取：

- `supported`：至少一条 `stance=support` 的证据支持该命题的完整范围、主体、客体、时间与模态，不只做主题相似匹配。
- `contradicted`：至少一条 `stance=reverse` 的证据直接给出与原命题相反的事实。缺少支持、没有测量、统计不显著，本身不是反向证据。
- `not_established`：源文未建立该命题。证据可只提供上下文并说明检索边界；不能将未知改写成已知否定。

顶层 verdict 由 components 的 disposition 集合确定，禁止凭总体印象判定：

| component disposition 集合 | 唯一允许的顶层 verdict |
| --- | --- |
| 仅 `supported` | `supported` |
| 仅 `contradicted` | `contradicted` |
| 仅 `not_established` | `not_established` |
| 两种或三种 disposition | `mixed` |

所以 `mixed` 必须至少有两个具有不同 disposition 的 components，不能仅因两个来源不同、语气复杂或证据很多就标为 `mixed`。输入 `compound=false` 时必须恰有一个 component；`compound=true` 时至少两个。即便一个连接词后的分句也 supported，另一个分句 reverse，仍应保留两条证据链，顶层才是 `mixed`。

## 3. 建议、提议、否定事实必须分流

- **不支持的建议或规范判断**（`claim_nature=recommendation`，如“应立即临床使用”）：没有疗效、安全性或适用性依据时，通常为 `not_established`，理由写“建议缺少支持”，不能伪造一个事实反命题而标 `contradicted`。
- **作为来源归属的提议**（`claim_nature=proposal_attribution`，如“作者提出未来研究低剂量”）：若源文确有该提议，可 `supported`；这只证明作者提出过，不证明提议内容有效。
- **不成立的负事实**（`claim_nature=negative_fact`，如“所有样本均未出现毒性”）：源文明确出现毒性时，是带 `reverse` 证据的 `contradicted`。
- **尚未知晓的负事实**（如“不能保持一年稳定性”，而只测试了24小时）：仍为 `not_established`，不能把证据缺口当反向证据。

因此，“提议尚无数据支持”这一事实若被草稿反述为“提议已有数据支持”，可 contradicted；但“应当采用该提议”这一规范建议在没有依据时是 not_established。二者必须分 component、分 `claim_nature`、分 rationale。

## 4. 语义不变量检查清单

每个 component 的 rationale 要明确处理下列相关维度：

1. **主客方向**：A 溶解 B 不等于 B 溶解 A；A 抑制 B 不等于 B 抑制 A。反转主体与客体不能沿用原证据。
2. **主动与被动**：被动句只改变语法焦点，不自动改变事件方向。“样品被 Lamp-L 加热”可与“Lamp-L 加热样品”等价。
3. **模态与强度**：“可能”“提示”“作者推断”不能升级为“证明”“必然”“已证实”。过强断言若源文没有建立强版本，通常 `not_established`；只有源文直接反对强版本时才 `contradicted`。
4. **来源时间层**：实验日期、发表日期、复测日期、草稿陈述的时态分别记录。2024 年测值不因2025年复述而变成2025年测值；旧结果也不自动代表新复测。
5. **跨来源冲突**：按各自来源、时间与条件分别裁决，不投票、不平均、不选择“更新者必胜”。同一并列句中一源支持、另一源反向，相应 components 导致 `mixed`，并在 `uncertainty` 记录未消解冲突。
6. **直接测量与作者推断**：“仪器直接测得 X”只有在源文明确报告直接测量时才可 supported。源文由阻抗谱、模型或拟合推断 X，只支持“作者推断 X”的归属命题，不支持“直接测量 X”，也不自动支持 X 的确定性事实。

## 5. 证据和 corrected claims

每条 evidence 含 `source_id`、原源文中的连续精确子串 `quote`、位置说明 `location`、`stance` 与必要的解释。`source_id` 必须存在于输入 `sources`，quote 必须能在该源文直接找到；不得仅给相似转述。`contradicted` component 必须有至少一条 `stance=reverse`；`supported` 必须有至少一条 `stance=support`。

`corrected_claim_ids` 只链接台账顶层 `corrected_claims` 中同 `input_id` 的修正建议。修正必须保留可核验边界，不能把不确定改成另一种确定。`review_disposition=reject` 表示该草稿断言不建议保留，它是编辑处置，不是运行状态；完整审计仍应 `status=success`。
